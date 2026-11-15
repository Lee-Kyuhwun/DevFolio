"""선택적 AI 보강 단계.

- 외부 AI 전송은 설정 동의가 있어야만 수행한다.
- AI 는 결정론적 분석의 근거 목록 밖의 내용을 주장할 수 없다(인용 ID 검증).
- AI 는 VERIFIED 등급을 만들 수 없다(최대 SUPPORTED_INFERENCE).
- 근거에 없는 숫자는 `[확인 필요]` 로 치환되고 HYPOTHESIS 로 내려간다.
- AI 실패 시 결정론적 결과는 그대로 보존하고 status=partial 로 표시한다.
"""

from __future__ import annotations

import json
from typing import Optional

from impactnote.core.intel.models import (
    Candidate,
    EvidenceRef,
    Finding,
    ProjectAnalysis,
)
from impactnote.core.metrics import sanitize_claims

MAX_PROMPT_CHARS = 16_000
MAX_CITATIONS = 28

SYSTEM_PROMPT = """당신은 소프트웨어 프로젝트의 개발 과정을 역추적하는 분석가입니다.

원칙:
1. 제공된 근거(문서·코드·커밋·측정값)에 없는 내용을 사실로 쓰지 않습니다.
2. 커밋 메시지는 단서일 뿐 성과의 증거가 아닙니다.
3. 문서에만 있고 코드에서 확인되지 않는 기능은 "미구현/가설"로 표시합니다.
4. 근거에 없는 숫자·개선율을 만들지 않습니다.
5. 확인된 사실, 근거 기반 추론, 추가 검증이 필요한 가설을 구분합니다.
6. 개인 기여는 커밋 작성자 정보만으로 단정하지 않습니다.

quality 는 HYPOTHESIS 또는 SUPPORTED_INFERENCE 만 사용하십시오(VERIFIED 금지).
"""

USER_PROMPT = """프로젝트: {project_name}
분석 범위: 문서 {doc_count}개, 코드 파일 {code_count}개, 커밋 {commit_count}개

[근거 목록]
{citations}

[결정론적 분석 요약]
{deterministic}

위 근거만 사용해 아래 JSON 을 작성하십시오.
{{
  "findings": [
    {{"title": "...", "detail": "...", "kind": "evolution|doc_only|code_only|conflict|risk",
      "quality": "SUPPORTED_INFERENCE|HYPOTHESIS", "citations": ["근거ID"]}}
  ],
  "candidates": [
    {{"title": "...", "problem": "...", "action": "...", "result": "...",
      "impact_categories": ["stability"], "quality": "SUPPORTED_INFERENCE|HYPOTHESIS",
      "citations": ["근거ID"]}}
  ],
  "notes": ["분석상 한계나 추가 확인이 필요한 점"]
}}
- result 에 수치를 쓰려면 근거에 그 수치가 그대로 있어야 합니다.
- 근거 ID 는 위 목록에 있는 값만 사용하십시오.
"""


def _citation_bundle(analysis: ProjectAnalysis) -> tuple[str, dict[str, EvidenceRef]]:
    refs: dict[str, EvidenceRef] = {}
    lines: list[str] = []
    for document in analysis.documents[:12]:
        ref = EvidenceRef(
            kind="document",
            title=f"{document.path} ({document.kind})",
            path=document.path,
            locator="문서",
            excerpt=document.excerpt[:1200],
            verified=not document.deleted,
        )
        refs[ref.id] = ref
        lines.append(
            f"[{ref.id}] DOC {document.path} | kind={document.kind}\n{document.summary[:300]}\n{document.excerpt[:900]}"
        )
    for code_file in sorted(
        analysis.code_files, key=lambda item: item.change_count, reverse=True
    )[:8]:
        ref = EvidenceRef(
            kind="code",
            title=f"{code_file.path}",
            path=code_file.path,
            locator=", ".join(code_file.symbols[:5]),
            excerpt=code_file.excerpt[:700],
            verified=True,
        )
        refs[ref.id] = ref
        lines.append(
            f"[{ref.id}] CODE {code_file.path} | symbols={', '.join(code_file.symbols[:8])}\n{code_file.excerpt[:700]}"
        )
    for commit in analysis.commits[:10]:
        ref = EvidenceRef(
            kind="commit",
            title=f"{commit.short} {commit.subject[:80]}",
            path=", ".join(commit.files[:3]),
            locator=commit.sha,
            excerpt=f"{commit.date} {commit.author} +{commit.insertions}/-{commit.deletions}",
            verified=True,
        )
        refs[ref.id] = ref
        lines.append(
            f"[{ref.id}] COMMIT {commit.short} {commit.date} {commit.author} | {commit.subject} | files={', '.join(commit.files[:3])}"
        )
    for measurement in analysis.measurements[:6]:
        ref = EvidenceRef(
            kind="measurement",
            title=f"{measurement.before} → {measurement.after}",
            path=measurement.source_path,
            locator=measurement.id,
            excerpt=measurement.conditions[:300],
            verified=measurement.verified,
        )
        refs[ref.id] = ref
        lines.append(
            f"[{ref.id}] MEASURE {measurement.before} -> {measurement.after} | {measurement.source_path}\n{measurement.conditions[:250]}"
        )

    text = "\n\n".join(lines)
    if len(text) > MAX_PROMPT_CHARS:
        text = text[:MAX_PROMPT_CHARS]
        keep = [ref_id for ref_id in refs if f"[{ref_id}]" in text]
        refs = {ref_id: refs[ref_id] for ref_id in keep}
    return text, refs


def _parse_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI 응답에서 JSON 객체를 찾지 못했습니다.")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("AI 응답이 JSON 객체가 아닙니다.")
    return payload


def _deterministic_summary(analysis: ProjectAnalysis) -> str:
    lines = [
        f"- 상태: {analysis.status}, 후보 {len(analysis.candidates)}건, "
        f"문서-코드 일치 {sum(1 for f in analysis.findings if f.kind == 'doc_code_match')}건, "
        f"문서만 존재 {sum(1 for f in analysis.findings if f.kind == 'doc_only')}건",
        f"- 측정값 {len(analysis.measurements)}건(검증 {sum(1 for m in analysis.measurements if m.verified)}건)",
    ]
    for candidate in analysis.candidates[:6]:
        lines.append(
            f"- 후보: {candidate.title} [{candidate.quality}] 근거 {len(candidate.evidence_ids)}건"
        )
    return "\n".join(lines)


def enrich_with_ai(
    analysis: ProjectAnalysis,
    *,
    store,
    provider: Optional[str] = None,
) -> ProjectAnalysis:
    analysis.ai.requested = True
    settings = store.settings()
    if not settings.external_ai_consent:
        analysis.ai.status = "skipped"
        analysis.ai.notes.append(
            "외부 AI 전송이 꺼져 있어 결정론적 분석만 수행했습니다(설정에서 동의 후 AI 보강 가능)."
        )
        return analysis

    citations, ref_map = _citation_bundle(analysis)
    if not citations.strip():
        analysis.ai.status = "skipped"
        analysis.ai.notes.append("AI 에 전달할 근거가 없어 보강을 건너뛰었습니다.")
        return analysis

    chosen = (provider or settings.default_provider or "").strip()
    if (
        settings.allowed_providers
        and chosen
        and chosen not in settings.allowed_providers
    ):
        analysis.ai.status = "failed"
        analysis.ai.error = f"허용되지 않은 Provider 입니다: {chosen}"
        analysis.status = "partial"
        analysis.warnings.append(analysis.ai.error)
        return analysis

    prompt = USER_PROMPT.format(
        project_name=analysis.project_name,
        doc_count=len(analysis.documents),
        code_count=len(analysis.code_files),
        commit_count=len(analysis.commits),
        citations=citations,
        deterministic=_deterministic_summary(analysis),
    )
    analysis.ai.prompt_chars = len(prompt)
    try:
        from devfolio.core.ai_observability import error_code_for, redact
        from devfolio.core.ai_reliability import classify_error
        from devfolio.core.ai_service import AIService
        from devfolio.core.storage import load_config

        telemetry: dict = {}
        raw = AIService(load_config())._call(
            SYSTEM_PROMPT,
            prompt,
            provider_name=chosen or None,
            max_tokens=2200,
            json_mode=True,
            telemetry=telemetry,
            stage="project_intel",
        )
        payload = _parse_json(raw)
        sources = [ref.excerpt for ref in ref_map.values()]
        added_findings = 0
        added_candidates = 0
        quality_map = {
            "SUPPORTED_INFERENCE": "SUPPORTED_INFERENCE",
            "HYPOTHESIS": "HYPOTHESIS",
            "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
            "VERIFIED": "SUPPORTED_INFERENCE",
        }

        def resolve(citations_value) -> list[str]:
            ids = [
                str(item) for item in (citations_value or []) if str(item) in ref_map
            ]
            return list(dict.fromkeys(ids))[:4]

        for item in payload.get("findings") or []:
            if not isinstance(item, dict) or added_findings >= 6:
                continue
            cited = resolve(item.get("citations"))
            if not cited:
                continue
            detail, dropped = sanitize_claims(str(item.get("detail") or ""), sources)
            quality = quality_map.get(str(item.get("quality")), "HYPOTHESIS")
            if dropped:
                quality = "HYPOTHESIS"
                detail += " (근거에 없는 수치는 제거됨)"
            analysis.findings.append(
                Finding(
                    title=str(item.get("title") or "AI 분석 항목")[:200],
                    detail=detail[:1200],
                    kind="evolution",
                    quality=quality,
                    paths=[ref_map[cid].path for cid in cited if ref_map[cid].path],
                    evidence_ids=cited,
                )
            )
            added_findings += 1

        for item in payload.get("candidates") or []:
            if not isinstance(item, dict) or added_candidates >= 6:
                continue
            cited = resolve(item.get("citations"))
            if not cited:
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            if any(
                title[:40] == existing.title[:40] for existing in analysis.candidates
            ):
                continue
            action, action_dropped = sanitize_claims(
                str(item.get("action") or ""), sources
            )
            result, result_dropped = sanitize_claims(
                str(item.get("result") or ""), sources
            )
            quality = quality_map.get(str(item.get("quality")), "HYPOTHESIS")
            if action_dropped or result_dropped:
                quality = "HYPOTHESIS"
            analysis.candidates.append(
                Candidate(
                    title=title[:200],
                    problem=str(item.get("problem") or "")[:800],
                    action=action[:1200],
                    result=result[:800],
                    impact_categories=[
                        str(value)
                        for value in (item.get("impact_categories") or [])[:3]
                    ],
                    quality=quality,
                    confidence=65 if quality == "SUPPORTED_INFERENCE" else 40,
                    evidence_ids=cited,
                    contribution={"role": "AI 제안 · 사용자 확인 필요"},
                    notes=[
                        "AI 보강 결과입니다. 인용 근거를 확인한 뒤 성과로 확정하세요."
                    ],
                )
            )
            added_candidates += 1

        for note in (payload.get("notes") or [])[:5]:
            analysis.ai.notes.append(str(note)[:400])
        analysis.ai.status = "completed"
        analysis.ai.used = True
        analysis.ai.provider = str(telemetry.get("provider", ""))
        analysis.ai.model = str(telemetry.get("model", ""))
        analysis.quality_summary = {
            level: sum(
                1 for candidate in analysis.candidates if candidate.quality == level
            )
            for level in (
                "VERIFIED",
                "SUPPORTED_INFERENCE",
                "HYPOTHESIS",
                "INSUFFICIENT_EVIDENCE",
            )
        }
    except Exception as exc:  # noqa: BLE001 — AI 실패가 결정론적 결과를 지우면 안 된다
        try:
            from devfolio.core.ai_observability import error_code_for, redact
            from devfolio.core.ai_reliability import classify_error

            analysis.ai.error = (
                f"{error_code_for(classify_error(exc), exc)}: {redact(str(exc), 200)}"
            )
        except Exception:
            analysis.ai.error = "AI 보강에 실패했습니다."
        analysis.ai.status = "failed"
        analysis.status = "partial"
        analysis.warnings.append(
            "AI 보강에 실패해 결정론적 분석 결과만 유지했습니다: " + analysis.ai.error
        )
    return analysis


__all__ = ["enrich_with_ai", "MAX_PROMPT_CHARS"]

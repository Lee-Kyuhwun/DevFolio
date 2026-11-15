"""성과 분석 AI — 기존 DevFolio 의 AI Reliability 자산을 그대로 재사용한다.

- 모델 체인·Fallback·Rate Limit·Cooldown·JSON 검증은 `devfolio.core.ai_service` 가 담당한다.
- 이 모듈은 "업무 기록 → 성과 구조" 프롬프트와 **전송 동의·근거 가드레일**만 추가한다.
- 원본 업무 기록은 절대 수정하지 않는다. 분석 결과는 별도 컬렉션에 저장한다.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from impactnote.core.metrics import sanitize_ai_result
from impactnote.core.models import AIAnalysis, Activity
from impactnote.core.service import ImpactService


class ConsentRequired(Exception):
    """외부 AI 전송 동의가 없을 때."""

    code = "EXTERNAL_AI_NOT_ALLOWED"


SYSTEM_PROMPT = """당신은 회사 업무 성과 정리 도우미입니다.
주어진 업무 기록만 근거로 사용하고, 기록에 없는 사실·수치·성과를 만들지 않습니다.
출력은 반드시 JSON 객체 하나이며, 마케팅 문구나 자기소개서 말투 대신 회사 내부 보고 문체를 씁니다."""

USER_PROMPT = """<activity>
제목: {title}
유형: {activity_type}
기간: {period}
프로젝트: {project}
수행 내용: {description}
문제/요구사항: {problem}
본인이 한 행동: {action}
정량/정성 결과(사용자 기록): {result}
협업: {collaborators}
연결된 근거:
{evidence}
</activity>

<rules>
- 기록에 있는 내용만 사용하세요. 없는 성과·수치를 추측하지 마세요.
- 숫자를 쓸 때는 위 기록에 그 숫자가 실제로 있을 때만 쓰세요.
- 팀 성과를 개인 성과로 표현하지 말고, 본인이 한 일과 공동 작업을 구분하세요.
- 결과가 기록에 없으면 result 를 빈 문자열로 두고, unverified_fields 에 "result" 를 넣으세요.
- impact_categories 는 다음 중에서만 고르세요: productivity, efficiency, stability, quality, cost,
  incident_prevention, automation, customer, schedule, risk, collaboration, technical, process
</rules>

<output_schema>
{{
  "title": "성과 제목(간결)",
  "problem": "해결하려던 문제",
  "action": "본인이 수행한 구체적 행동",
  "result": "기록된 결과(없으면 빈 문자열)",
  "impact_categories": ["..."],
  "organization_value": "조직에 남긴 가치(기록 근거 범위 내)",
  "contribution": {{"role": "본인 역할", "solo": ["..."], "shared": ["..."], "decisions": ["..."]}},
  "evidence_check": "근거가 충분한지 한 문장",
  "unverified_fields": ["..."],
  "statements": {{
    "weekly": "업무보고용 한 문장",
    "monthly": "월간 실적용 요약",
    "self_review": "자기평가용 문장",
    "executive": "임원 보고용 핵심 한 줄"
  }}
}}
</output_schema>"""


def _parse_json(raw: str) -> dict:
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI 응답에서 JSON 객체를 찾지 못했습니다.")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("AI 응답이 JSON 객체가 아닙니다.")
    return payload


def _evidence_text(service: ImpactService, activity: Activity) -> tuple[str, list[str]]:
    evidence = service.evidence_map()
    lines: list[str] = []
    sources: list[str] = []
    for evidence_id in activity.evidence_ids:
        item = evidence.get(evidence_id)
        if item is None:
            continue
        lines.append(
            f"- [{item.type}] {item.title} {item.reference} {item.description}".strip()
        )
        sources.append(f"{item.title} {item.reference} {item.description}")
    if not lines:
        lines.append("- (연결된 근거 없음)")
    return "\n".join(lines), sources


def analyze_activity(
    service: ImpactService,
    activity_id: str,
    *,
    provider: Optional[str] = None,
) -> AIAnalysis:
    """업무 기록 1건을 성과 구조로 분석한다. 실패해도 원본은 그대로 남는다."""
    activity = service.activity(activity_id)
    settings = service.settings()
    if not settings.external_ai_consent:
        raise ConsentRequired(
            "외부 AI 전송이 꺼져 있습니다. 설정에서 동의한 뒤 다시 시도하세요."
        )
    chosen = (provider or settings.default_provider or "").strip()
    if (
        settings.allowed_providers
        and chosen
        and chosen not in settings.allowed_providers
    ):
        raise ConsentRequired(
            f"허용되지 않은 Provider 입니다: {chosen}. 설정의 허용 목록을 확인하세요."
        )

    evidence_text, evidence_sources = _evidence_text(service, activity)
    sources = [
        activity.title,
        activity.description,
        activity.problem,
        activity.action,
        activity.project,
        *evidence_sources,
    ]
    analysis = AIAnalysis(activity_id=activity.id, status="completed")
    try:
        from devfolio.core.ai_observability import error_code_for, redact
        from devfolio.core.ai_reliability import classify_error
        from devfolio.core.ai_service import AIService
        from devfolio.core.storage import load_config

        telemetry: dict = {}
        raw = AIService(load_config())._call(
            SYSTEM_PROMPT,
            USER_PROMPT.format(
                title=activity.title,
                activity_type=activity.activity_type,
                period=activity.date
                + (f" ~ {activity.period_end}" if activity.period_end else ""),
                project=activity.project or "(없음)",
                description=activity.description or "(없음)",
                problem=activity.problem or "(없음)",
                action=activity.action or "(없음)",
                result=activity.result or "(기록 없음)",
                collaborators=", ".join(activity.collaborators) or "(없음)",
                evidence=evidence_text,
            ),
            provider_name=chosen or None,
            max_tokens=1600,
            json_mode=True,
            telemetry=telemetry,
            stage="achievement_analysis",
        )
        parsed = _parse_json(raw)
        cleaned, removed = sanitize_ai_result(parsed, sources)
        cleaned["unverified_metrics"] = removed
        analysis.result = cleaned
        analysis.provider = str(telemetry.get("provider", ""))
        analysis.model = str(telemetry.get("model", ""))
        analysis.status = "completed"
    except Exception as exc:  # noqa: BLE001 — 분석 실패가 기록을 막으면 안 된다
        try:
            from devfolio.core.ai_observability import error_code_for, redact
            from devfolio.core.ai_reliability import classify_error

            analysis.error_code = error_code_for(classify_error(exc), exc)
            analysis.error_message = redact(str(exc), 200)
        except Exception:
            analysis.error_code = "UNKNOWN_ERROR"
            analysis.error_message = "AI 분석에 실패했습니다."
        analysis.status = "failed"
    service.save_analysis(analysis)
    return analysis


GIT_KEYWORDS = (
    "fix",
    "bug",
    "hotfix",
    "장애",
    "오류",
    "수정",
    "개선",
    "성능",
    "최적화",
    "리팩터",
    "refactor",
    "ci",
    "cd",
    "배포",
    "자동화",
    "테스트",
    "보안",
    "feat",
    "기능",
)


def suggest_from_git(
    service: ImpactService,
    *,
    repo_path: str,
    author_email: str,
    limit: int = 20,
) -> dict:
    """Git 커밋에서 업무 기록·성과 후보를 수집한다(사실 확정 아님, 검토 필요).

    AI 를 호출하지 않는다 — 커밋 메시지와 파일 변경만으로 후보를 만들고,
    모든 후보는 `needs_review` 상태로 저장해 사용자가 확인하게 한다.
    """
    from pathlib import Path

    from devfolio.core.git_scanner import scan_repo

    result = scan_repo(Path(repo_path), author_email=author_email, analyze=False)
    existing_refs = {
        item.source_ref for item in service.activities() if item.source_ref
    }
    created_activities = 0
    created_achievements = 0

    for commit in result.commits[: max(1, limit)]:
        ref = f"git:{result.repo_name}:{commit.sha}"
        if ref in existing_refs:
            continue
        subject = (commit.subject or "").strip()
        kind = (
            "incident"
            if any(
                word in subject.lower() for word in ("fix", "hotfix", "장애", "오류")
            )
            else "performance"
            if any(word in subject.lower() for word in ("성능", "최적화", "자동화"))
            else "feature"
        )
        evidence = service.create_evidence(
            {
                "type": "git_commit",
                "title": f"커밋 {commit.sha[:8]}: {subject[:80]}",
                "reference": f"{result.repo_url or repo_path}#{commit.sha}",
                "description": f"{commit.date} / {commit.author_name} / +{commit.insertions} -{commit.deletions}",
                "verified": True,
            }
        )
        activity = service.create_activity(
            {
                "title": subject[:200] or f"커밋 {commit.sha[:8]}",
                "description": f"{commit.date} 커밋 · 변경 파일 {commit.files_changed}개",
                "date": commit.date,
                "project": result.repo_name,
                "activity_type": kind,
                "status": "done",
                "evidence_ids": [evidence.id],
                "source": "git",
                "source_ref": ref,
                "tags": ["git", "자동수집"],
            }
        )
        created_activities += 1
        lowered = subject.lower()
        if any(keyword in lowered for keyword in GIT_KEYWORDS):
            service.create_achievement(
                {
                    "title": f"성과 후보: {subject}"[:200],
                    "activity_ids": [activity.id],
                    "action": subject,
                    "evidence_ids": [evidence.id],
                    "source": "git",
                    "status": "needs_review",
                    "needs_review": True,
                    "period_start": commit.date,
                    "period_end": commit.date,
                }
            )
            created_achievements += 1

    return {
        "repo": result.repo_name,
        "scanned_commits": len(result.commits),
        "created_activities": created_activities,
        "created_candidates": created_achievements,
        "note": "자동 수집 결과는 검토 필요 상태입니다. 근거를 확인한 뒤 성과로 확정하세요.",
    }


__all__ = ["ConsentRequired", "analyze_activity", "suggest_from_git"]

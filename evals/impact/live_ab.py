"""실제 NVIDIA 소규모 A/B — 정성 효과 Hard Gate 의 증분 효과.

동일 모델·동일 프롬프트·동일 입력에서 한 번의 호출 결과를 두 방식으로 저장한다.

- Baseline: 수치 가드레일만 적용 (개선 전 저장 방식)
- Variant : 수치 가드레일 + 정성 효과 Hard Gate (이번 개선)

한 번에 한 조건만 바꾸므로 Gate 의 효과를 분리해 측정할 수 있다.
호출은 활동 1건당 1회이며, 결과를 매 행마다 파일에 기록한다.

    ./.venv/bin/python -m evals.impact.live_ab --out /tmp/impact-live-ab
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from evals.impact.run import DATASET_PATH, _load_dataset, _restricted_nvidia_service
from impactnote.core.claims import find_effect_claims, gate_result, verify_effect_claim
from impactnote.core.metrics import sanitize_ai_result


def _unsupported_effects(text: str, source: str) -> list[dict]:
    rows: list[dict] = []
    for sentence in find_effect_claims(text):
        verdict = verify_effect_claim(sentence, [source])
        if verdict is not None and not verdict.supported:
            rows.append(verdict.as_dict())
    return rows


def run(*, out_dir: Path, limit: Optional[int] = None) -> dict:
    from impactnote.core.ai import SYSTEM_PROMPT, USER_PROMPT, _parse_json

    dataset = _load_dataset(DATASET_PATH)
    activities = dataset["live_activities"][: limit or len(dataset["live_activities"])]
    service = _restricted_nvidia_service()
    if service is None:
        raise SystemExit("nvidia_nim provider 가 설정되지 않았습니다.")
    os.environ["DEVFOLIO_AI_PROVIDER_FALLBACK"] = "0"
    os.environ.setdefault("DEVFOLIO_AI_TIME_BUDGET", "120")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for activity in activities:
        values = activity["input"]
        telemetry: dict = {}
        started = time.monotonic()
        row: dict = {
            "id": activity["id"],
            "model": "nvidia_nim/openai/gpt-oss-20b",
            "prompt_version": "evidence-grounded-v2",
        }
        try:
            raw = service._call(
                SYSTEM_PROMPT,
                USER_PROMPT.format(
                    title=values["title"],
                    activity_type=values["activity_type"],
                    period=values["period"],
                    project=values["project"],
                    description=values["description"],
                    problem=values["problem"],
                    action=values["action"],
                    result=values["result"] or "(기록 없음)",
                    collaborators=values["collaborators"] or "(없음)",
                    evidence=values["evidence"],
                ),
                provider_name="nvidia_nim",
                max_tokens=1600,
                json_mode=True,
                telemetry=telemetry,
                stage="impact_live_ab",
            )
            row["latency_ms"] = round((time.monotonic() - started) * 1000)
            row["usage"] = telemetry.get("usage") or {}
            payload = _parse_json(raw)
            source = " ".join(str(value) for value in values.values())
            raw_text = json.dumps(payload, ensure_ascii=False)
            baseline, baseline_numbers = sanitize_ai_result(payload, [source])
            baseline_text = json.dumps(baseline, ensure_ascii=False)
            variant, variant_numbers = sanitize_ai_result(payload, [source])
            variant, blocked = gate_result(variant, [source])
            variant_text = json.dumps(variant, ensure_ascii=False)
            row.update(
                {
                    "status": "LIVE_VERIFIED",
                    "raw_effect_claims": len(find_effect_claims(raw_text)),
                    "raw_unsupported_effects": len(
                        _unsupported_effects(raw_text, source)
                    ),
                    "baseline_effect_claims": len(find_effect_claims(baseline_text)),
                    "baseline_unsupported_effects": len(
                        _unsupported_effects(baseline_text, source)
                    ),
                    "variant_effect_claims": len(find_effect_claims(variant_text)),
                    "variant_unsupported_effects": len(
                        _unsupported_effects(variant_text, source)
                    ),
                    "gate_blocked_claims": len(blocked),
                    "numeric_replacements": len(baseline_numbers)
                    + len(variant_numbers),
                    "forbidden_hits": [
                        pattern
                        for pattern in activity.get("forbidden_patterns", [])
                        if pattern.lower() in raw.lower()
                    ],
                    "raw_text": raw_text[:3000],
                }
            )
        except Exception as exc:  # noqa: BLE001 — 실패도 기록한다
            row.update(
                {
                    "status": "FAILED",
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                    "telemetry": {
                        key: telemetry.get(key)
                        for key in ("provider", "model", "attempts", "errors")
                        if telemetry.get(key) is not None
                    },
                }
            )
        rows.append(row)
        (out_dir / "live-ab.json").write_text(
            json.dumps(
                {
                    "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    ok = [row for row in rows if row["status"] == "LIVE_VERIFIED"]
    summary = {
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": "nvidia_nim/openai/gpt-oss-20b",
        "n": len(rows),
        "succeeded": len(ok),
        "failed": len(rows) - len(ok),
        "mean_latency_ms": (
            sum(row["latency_ms"] for row in ok) / len(ok) if ok else None
        ),
        "total_prompt_tokens": sum(
            int((row.get("usage") or {}).get("prompt_tokens") or 0) for row in ok
        ),
        "total_completion_tokens": sum(
            int((row.get("usage") or {}).get("completion_tokens") or 0) for row in ok
        ),
        "baseline_unsupported_effects": sum(
            row.get("baseline_unsupported_effects", 0) for row in ok
        ),
        "variant_unsupported_effects": sum(
            row.get("variant_unsupported_effects", 0) for row in ok
        ),
        "gate_blocked_claims": sum(row.get("gate_blocked_claims", 0) for row in ok),
        "rows": rows,
    }
    (out_dir / "live-ab.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 실제 NVIDIA A/B — 정성 효과 Hard Gate",
        "",
        f"- 실행: {summary['run_at']}",
        f"- 모델: `{summary['model']}`",
        f"- 성공/전체: {summary['succeeded']}/{summary['n']}",
        f"- 평균 지연: {int(summary['mean_latency_ms']) if summary['mean_latency_ms'] else 'NOT_MEASURED'} ms",
        "",
        "| ID | raw 근거없는 효과 | Baseline 저장 | Variant 저장 | Gate 차단 |",
        "|---|---|---|---|---|",
        *[
            f"| {row.get('id')} | {row.get('raw_unsupported_effects', 'FAILED')} | "
            f"{row.get('baseline_unsupported_effects', '-')} | "
            f"{row.get('variant_unsupported_effects', '-')} | "
            f"{row.get('gate_blocked_claims', '-')} |"
            for row in rows
        ],
        "",
        f"- Baseline 저장 후 근거 없는 효과 주장: **{summary['baseline_unsupported_effects']}건**",
        f"- Variant 저장 후 근거 없는 효과 주장: **{summary['variant_unsupported_effects']}건**",
    ]
    (out_dir / "live-ab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="NVIDIA 소규모 A/B")
    parser.add_argument("--out", type=Path, default=Path("/tmp/impact-live-ab"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    summary = run(out_dir=args.out, limit=args.limit)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()

"""사람 라벨과 심사 모델 판정을 비교해 보고서를 만들고, 사전 등록 규칙으로 판정한다.

python -m evals.report evals/runs/<run_id>   → <run_id>/report.md
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from evals.label import _read_jsonl
from evals.metrics import (
    AGREEMENT_THRESHOLD,
    FACTUALITY_MISS_THRESHOLD,
    agreement,
    cohen_kappa,
    decide,
    miss_rate,
)


def _pct(value: float | None) -> str:
    return "계산 불가" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None) -> str:
    return "계산 불가" if value is None else f"{value:.2f}"


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_report(outputs: list[dict], labels: list[dict]) -> str:
    ok = [row for row in outputs if not row.get("error")]
    errors = [row for row in outputs if row.get("error")]
    label_by_id = {label["output_id"]: label for label in labels}
    paired = [
        (row, label_by_id[row["output_id"]])
        for row in ok
        if row["output_id"] in label_by_id
    ]
    missing = [row for row in ok if row["output_id"] not in label_by_id]

    # (사람, 심사 모델) 판정 쌍
    axes = {
        "factuality": [
            (lab["has_unsupported"], row["judge_scores"].get("factuality", 5) < 3)
            for row, lab in paired
        ],
        "naturalness": [
            (lab["naturalness"] >= 4, row["judge_scores"].get("naturalness", 0) >= 4)
            for row, lab in paired
        ],
        "pass": [
            (lab["usability"] == "as_is", bool(row["judge_passed"]))
            for row, lab in paired
        ],
    }
    agreements = {axis: agreement(pairs) for axis, pairs in axes.items()}
    fact_miss = miss_rate(
        [human for human, _ in axes["factuality"]],
        [judge for _, judge in axes["factuality"]],
    )
    decisions = decide(agreements, fact_miss)

    lines = [
        "# AI 심사 신뢰도 측정 보고서",
        "",
        "## 1. 표본",
        "",
        f"- 라벨 {len(paired)} / 전체 {len(ok)} (오류 {len(errors)}건 제외)",
        "- 소규모 파일럿이다. 수치는 이 표본에서만 유효하다.",
        "",
        "## 2. 항목별 일치율 (사람 vs 심사 모델)",
        "",
        "| 항목 | 사람 기준 | 심사 모델 기준 | n | 일치율 | kappa |",
        "|---|---|---|---|---|---|",
        f"| factuality | 근거 없는 사실 있음 | factuality < 3 | {len(axes['factuality'])} | "
        f"{_pct(agreements['factuality'])} | {_num(cohen_kappa(axes['factuality']))} |",
        f"| naturalness | 자연스러움 ≥ 4 | naturalness ≥ 4 | {len(axes['naturalness'])} | "
        f"{_pct(agreements['naturalness'])} | {_num(cohen_kappa(axes['naturalness']))} |",
        f"| pass | 그대로 사용 | 심사 통과 | {len(axes['pass'])} | "
        f"{_pct(agreements['pass'])} | {_num(cohen_kappa(axes['pass']))} |",
        "",
        "## 3. 심사 모델이 놓친 근거 없는 사실",
        "",
        f'- 사람이 "근거 없는 사실 있음"으로 본 출력 중 심사 모델이 놓친 비율: **{_pct(fact_miss)}**',
        "- 결정적 근거 검사기의 재현율·정밀도는 근거 검사 구현 후 추가한다.",
        "",
        "## 4. 판정 (데이터를 보기 전에 정한 규칙)",
        "",
        f"- 일치율 ≥ {AGREEMENT_THRESHOLD:.0%} → auto, 미만 → human_required, 계산 불가 → undetermined",
        f"- factuality 놓친 비율 > {FACTUALITY_MISS_THRESHOLD:.0%} → human_required",
        "",
        "| 항목 | 판정 |",
        "|---|---|",
        *[f"| {axis} | {decisions[axis]} |" for axis in axes],
        "",
        "## 5. 전략별 비교",
        "",
        '| 전략 | 출력 | 평균 호출 | 평균 지연(초) | 심사 통과율 | 사람 "그대로 사용" |',
        "|---|---|---|---|---|---|",
    ]

    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for row in ok:
        by_strategy[row["strategy"]].append(row)
    for strategy, rows in by_strategy.items():
        calls = _mean([r["calls"] for r in rows])
        latency = _mean([r["latency_ms"] / 1000 for r in rows])
        judge_pass = _mean([1.0 if r["judge_passed"] else 0.0 for r in rows])
        usable = [
            1.0 if label_by_id[r["output_id"]]["usability"] == "as_is" else 0.0
            for r in rows
            if r["output_id"] in label_by_id
        ]
        lines.append(
            f"| {strategy} | {len(rows)} | {_num(calls)} | {_num(latency)} | "
            f"{_pct(judge_pass)} | {_pct(_mean(usable))} |"
        )

    warnings = [
        f"- 전략 변경: {row['output_id'].split(':')[0]} {row['strategy']} → {row['resolved_strategy']}"
        for row in ok
        if row.get("resolved_strategy") and row["strategy"] != row["resolved_strategy"]
    ]
    if missing:
        warnings.append(f"- 라벨 누락 {len(missing)}건")
    if errors:
        warnings.append(
            f"- 생성 오류 {len(errors)}건: " + ", ".join(r["output_id"] for r in errors)
        )
    lines += ["", "## 6. 경고", "", *(warnings or ["- 없음"]), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI 심사 신뢰도 측정: 보고서")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)

    report = build_report(
        _read_jsonl(args.run_dir / "outputs.jsonl"),
        _read_jsonl(args.run_dir / "labels.jsonl"),
    )
    out = args.run_dir / "report.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()

"""사람이 생성 결과를 블라인드로 채점한다. 전략명·심사 점수·출력 ID는 보여주지 않는다.

    python -m evals.label evals/runs/<run_id> [--cases evals/cases]

한 건마다 labels.jsonl에 바로 기록하므로 중간에 멈춰도 다시 실행하면 이어서 한다.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Callable

from devfolio.core.ai_service import AIService, _prune_empty
from devfolio.models.config import Config
from devfolio.models.project import Project

_USABILITY = {"1": "as_is", "2": "needs_edit", "3": "unusable"}


def pending_items(outputs: list[dict], labeled_ids: set[str], seed: str) -> list[dict]:
    """오류 행과 이미 라벨한 항목을 빼고, seed로 고정된 순서로 섞는다."""
    items = [
        row
        for row in outputs
        if not row.get("error") and row["output_id"] not in labeled_ids
    ]
    items.sort(key=lambda row: row["output_id"])
    random.Random(seed).shuffle(items)
    return items


def _ask_until(
    ask: Callable[[str], str], prompt: str, valid: Callable[[str], bool]
) -> str:
    answer = ask(prompt).strip()
    while not valid(answer):
        answer = ask("다시 입력하세요. " + prompt).strip()
    return answer


def label_one(item: dict, evidence_summary: str, ask: Callable[[str], str]) -> dict:
    """한 건을 채점한다. 화면에는 evidence와 생성된 요약만 보여준다."""
    header = (
        "=== evidence (생성·심사 모델이 받은 사실) ===\n"
        f"{evidence_summary}\n\n"
        "=== 생성된 요약 ===\n"
        f"{item['text']}\n\n"
    )
    has = (
        _ask_until(
            ask,
            header + "evidence에 없는 사실이 있나요? [y/n]: ",
            lambda a: a.lower() in ("y", "n"),
        ).lower()
        == "y"
    )
    unsupported_text = ask("어떤 표현인가요? (쉼표로 구분): ").strip() if has else ""
    naturalness = int(
        _ask_until(ask, "자연스러움 1~5: ", lambda a: a in {"1", "2", "3", "4", "5"})
    )
    usability = _USABILITY[
        _ask_until(
            ask,
            "그대로 쓸 수 있나요? 1=그대로 사용 2=수정 필요 3=사용 불가: ",
            lambda a: a in _USABILITY,
        )
    ]
    return {
        "output_id": item["output_id"],
        "has_unsupported": has,
        "unsupported_text": unsupported_text,
        "naturalness": naturalness,
        "usability": usability,
    }


def evidence_summary(project: Project) -> str:
    """생성·심사 모델이 받은 것과 같은 evidence를 사람이 읽을 수 있게 보여준다."""
    evidence = AIService(Config()).build_evidence(project=project)
    # 생성·심사 프롬프트와 같은 방식으로 직렬화한다 (기본값과 같은 필드도 포함).
    payload = _prune_empty(evidence.model_dump(exclude_none=True))
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def main(argv: list[str] | None = None) -> None:
    from evals.run import load_cases

    parser = argparse.ArgumentParser(description="AI 심사 신뢰도 측정: 블라인드 라벨링")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--cases", type=Path, default=Path("evals/cases"))
    args = parser.parse_args(argv)

    outputs = _read_jsonl(args.run_dir / "outputs.jsonl")
    labels_path = args.run_dir / "labels.jsonl"
    labeled = {row["output_id"] for row in _read_jsonl(labels_path)}
    summaries = {case_id: evidence_summary(p) for case_id, p in load_cases(args.cases)}
    items = pending_items(outputs, labeled, seed=args.run_dir.name)

    total = len(labeled) + len(items)
    print(
        f"라벨 {len(labeled)}/{total}건 완료. 남은 {len(items)}건을 시작합니다. (Ctrl+C로 중단 가능)"
    )
    with labels_path.open("a", encoding="utf-8") as fh:
        for n, item in enumerate(items, start=len(labeled) + 1):
            print(f"\n----- [{n}/{total}] -----")
            label = label_one(
                item, summaries.get(item["case_id"], "(사례 없음)"), input
            )
            fh.write(json.dumps(label, ensure_ascii=False) + "\n")
            fh.flush()
    print(f"\n완료. 다음 단계: python -m evals.report {args.run_dir}")


if __name__ == "__main__":
    main()

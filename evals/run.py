"""사례 × 생성 전략으로 요약을 만들고 심사 모델 판정을 기록한다.

    python -m evals.run --cases evals/cases --strategies single,best_of_n,s1_refine,hybrid --provider pollinations

최종 수정·최종 판정 전에 선택된 후보를 기록한다(`AIService._select_best_candidate`).
심사 모델이 불합격시킨 출력도 남겨야 사람 판정과 치우침 없이 비교할 수 있다.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ruamel.yaml import YAML

from devfolio.core.ai_service import AIService, GenerationProfile
from devfolio.exceptions import DevfolioError
from devfolio.models.config import Config
from devfolio.models.project import Project

# 전략별 reasoning 설정. best_of_n·hybrid는 samples가 2 미만이면 single로 바뀌므로 3으로 고정한다.
STRATEGIES: dict[str, dict[str, int]] = {
    "single": {"samples": 1, "refinement_budget": 0},
    "best_of_n": {"samples": 3, "refinement_budget": 0},
    "s1_refine": {"samples": 1, "refinement_budget": 2},
    "hybrid": {"samples": 3, "refinement_budget": 1},
}

# 사례 1개당 전략별 최대 AI 호출 수 (생성 + 심사 + 수정 + 최종 심사 상한)
_MAX_CALLS = {"single": 4, "best_of_n": 8, "s1_refine": 8, "hybrid": 14}

_PROFILE = GenerationProfile(mode="project_summary", language="ko", max_tokens=2800)


class CountingAIService(AIService):
    """AI 호출 수와 누적 지연 시간을 센다."""

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.calls = 0
        self.latency_ms = 0

    def _call_messages(self, *args, **kwargs) -> str:
        self.calls += 1
        started = time.monotonic()
        try:
            return super()._call_messages(*args, **kwargs)
        finally:
            self.latency_ms += int((time.monotonic() - started) * 1000)


def load_cases(directory: Path) -> list[tuple[str, Project]]:
    """디렉터리의 *.yaml을 Project로 읽는다. case_id는 파일 이름(확장자 제외)."""
    yaml = YAML(typ="safe")
    cases = []
    for path in sorted(Path(directory).glob("*.yaml")):
        data = yaml.load(path.read_text(encoding="utf-8"))
        cases.append((path.stem, Project.model_validate(data)))
    return cases


def estimate_max_calls(n_cases: int, strategies: list[str]) -> int:
    return n_cases * sum(_MAX_CALLS[s] for s in strategies)


def _config_for(config: Config, strategy: str) -> Config:
    cfg = config.model_copy(deep=True)
    cfg.reasoning = cfg.reasoning.model_copy(
        update={"strategy": strategy, **STRATEGIES[strategy]}
    )
    return cfg


def run_eval(
    cases: list[tuple[str, Project]],
    strategies: list[str],
    config: Config,
    provider: Optional[str],
    out_dir: Path,
) -> Path:
    """결과를 out_dir/outputs.jsonl에 한 줄씩 기록하고 그 경로를 반환한다(중단돼도 앞부분은 남는다)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "outputs.jsonl"
    with out_path.open("a", encoding="utf-8") as fh:
        for case_id, project in cases:
            for strategy in strategies:
                service = CountingAIService(_config_for(config, strategy))
                row: dict = {
                    "output_id": f"{case_id}:{strategy}",
                    "case_id": case_id,
                    "strategy": strategy,
                    "resolved_strategy": None,
                    "text": "",
                    "judge_scores": {},
                    "judge_passed": None,
                    "calls": 0,
                    "latency_ms": 0,
                    "error": None,
                }
                try:
                    evidence = service.build_evidence(project=project)
                    candidate, plan = service._select_best_candidate(
                        evidence=evidence,
                        profile=_PROFILE,
                        provider_name=provider,
                        samples=None,
                    )
                    row.update(
                        resolved_strategy=plan.strategy,
                        text=candidate.draft,
                        judge_scores=dict(candidate.review.scores),
                        judge_passed=candidate.review.passed,
                    )
                except DevfolioError as e:
                    row["error"] = str(e)
                row.update(calls=service.calls, latency_ms=service.latency_ms)
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                print(
                    f"[{row['output_id']}] calls={row['calls']} "
                    f"{'ERROR ' + row['error'] if row['error'] else 'ok'}"
                )
    return out_path


def main(argv: Optional[list[str]] = None) -> None:
    from devfolio.core.storage import load_config

    parser = argparse.ArgumentParser(description="AI 심사 신뢰도 측정: 생성·심사 실행")
    parser.add_argument("--cases", type=Path, default=Path("evals/cases"))
    parser.add_argument("--strategies", default=",".join(STRATEGIES))
    parser.add_argument("--provider", default="pollinations")
    parser.add_argument("--yes", action="store_true", help="AI 호출 확인 생략")
    args = parser.parse_args(argv)

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    unknown = [s for s in strategies if s not in STRATEGIES]
    if unknown:
        parser.error(f"알 수 없는 전략: {unknown}")
    cases = load_cases(args.cases)
    if not cases:
        parser.error(f"사례가 없습니다: {args.cases}/*.yaml")

    print(
        f"사례 {len(cases)}개 × 전략 {len(strategies)}개 = 출력 {len(cases) * len(strategies)}개"
    )
    print(
        f"예상 최대 AI 호출: {estimate_max_calls(len(cases), strategies)}회 (provider: {args.provider})"
    )
    if not args.yes and input("실행할까요? [y/N] ").strip().lower() != "y":
        print("취소했습니다.")
        return

    out_dir = Path("evals/runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = run_eval(cases, strategies, load_config(), args.provider, out_dir)
    print(f"완료: {out_path}")
    print(f"다음 단계: python -m evals.label {out_dir}")


if __name__ == "__main__":
    main()

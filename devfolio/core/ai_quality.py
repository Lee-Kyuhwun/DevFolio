"""AI 분석 결과의 품질 하한선 — 결정론적 검증 계층.

[Spring 비교]
  @Valid + 커스텀 Validator 조합과 같다. AI 응답을 "요청 성공 = 분석 성공"으로
  취급하지 않기 위해, 생성 결과를 코드로 다시 검증한다.

세 계층으로 나눈다.
  Level 1 (기술적 유효성): 스키마·필수 필드·타입. 하나라도 실패하면 승인하지 않는다.
  Level 2 (내용 신뢰성): 저장소 근거로 확인되지 않는 기술·수치를 찾아낸다.
  Level 3 (포트폴리오 품질): 기존 ReviewResult(심사) 를 그대로 재사용한다.

원칙:
  - 점수는 보조 지표다. 근거 불일치·허위 수치는 점수와 무관한 Hard Gate 로 막는다.
  - AI 로 판정하지 않는다. 같은 입력이면 항상 같은 결과가 나와야 테스트가 가능하다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# 숫자 + 단위. 커밋 수·LOC 처럼 근거 없이 만들기 쉬운 성과 표현을 잡는다.
_METRIC_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(%|퍼센트|배|초|ms|밀리초|분|시간|건|개|명|줄|라인|LOC)"
)

# 분석 결과에서 문장 검증 대상이 되는 필드.
_PROSE_FIELDS = ("purpose", "problem", "solution", "summary")

_REQUIRED_TEXT_FIELDS = ("project_type", "purpose", "problem", "solution", "summary")
_REQUIRED_LIST_FIELDS = ("key_features", "tech_stack", "tasks")
_TASK_TEXT_FIELDS = ("name", "problem", "solution")


@dataclass(frozen=True)
class QualityIssue:
    level: int
    code: str
    field: str
    message: str
    hard: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "hard": self.hard,
        }


@dataclass
class QualityReport:
    """분석 결과 검증 리포트. 사용자 화면과 로그에 그대로 쓸 수 있는 형태."""

    level1_ok: bool = True
    level2_ok: bool = True
    review_passed: Optional[bool] = None
    issues: list[QualityIssue] = field(default_factory=list)
    techs_supported: int = 0
    techs_total: int = 0

    @property
    def hard_failures(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.hard]

    @property
    def passed(self) -> bool:
        return self.level1_ok and self.level2_ok and not self.hard_failures

    @property
    def verdict(self) -> str:
        if self.passed:
            return "passed"
        if not self.level1_ok:
            return "rejected_schema"
        return "rejected_evidence"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "passed": self.passed,
            "level1_ok": self.level1_ok,
            "level2_ok": self.level2_ok,
            "review_passed": self.review_passed,
            "techs_supported": self.techs_supported,
            "techs_total": self.techs_total,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def summary(self) -> str:
        if self.passed:
            return "품질 검증 통과"
        codes = ", ".join(sorted({issue.code for issue in self.issues})) or "unknown"
        return f"품질 검증 실패({self.verdict}): {codes}"


@dataclass(frozen=True)
class EvidenceIndex:
    """저장소에서 확인된 사실만 모은 색인. AI 생성 내용과 대조하는 기준이다."""

    haystack: str
    techs: frozenset[str]

    def mentions(self, token: str) -> bool:
        token = token.strip().lower()
        if not token or len(token) < 2:
            return True
        return token in self.haystack

    def mentions_number(self, number: str) -> bool:
        return number in self.haystack


def build_evidence_index(
    project_context: Optional[dict[str, Any]] = None,
    scan_metrics: Optional[dict[str, Any]] = None,
) -> EvidenceIndex:
    """README·의존성·언어·파일 경로에서 검증 가능한 근거 색인을 만든다."""
    context = project_context or {}
    metrics = scan_metrics or {}

    parts: list[str] = []
    readme = context.get("readme") or ""
    if isinstance(readme, str):
        parts.append(readme)

    dependencies = context.get("dependencies") or {}
    techs: set[str] = set()
    if isinstance(dependencies, dict):
        for packages in dependencies.values():
            for package in packages or []:
                name = str(package).strip().lower()
                if not name:
                    continue
                techs.add(name)
                # `uvicorn[standard]` 같은 extras 표기도 이름만 남긴다.
                techs.add(re.split(r"[\[<>=!~ ]", name)[0])
                parts.append(name)

    key_files = context.get("key_files") or {}
    if isinstance(key_files, dict):
        for path in list(key_files)[:50]:
            parts.append(str(path))

    languages = context.get("languages") or {}
    if isinstance(languages, dict):
        parts.extend(str(name) for name in languages)

    scan_languages = metrics.get("languages") or {}
    if isinstance(scan_languages, dict):
        parts.extend(str(name) for name in scan_languages)
    if metrics.get("commits"):
        parts.append(str(metrics["commits"]))

    haystack = "\n".join(parts).lower()
    return EvidenceIndex(haystack=haystack, techs=frozenset(techs))


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_level1(payload: dict[str, Any], report: QualityReport) -> None:
    for name in _REQUIRED_TEXT_FIELDS:
        if not _is_text(payload.get(name)):
            report.issues.append(
                QualityIssue(
                    level=1,
                    code="missing_field",
                    field=name,
                    message=f"{name} 값이 비어 있습니다.",
                    hard=True,
                )
            )
    for name in _REQUIRED_LIST_FIELDS:
        value = payload.get(name)
        if not isinstance(value, list) or not value:
            report.issues.append(
                QualityIssue(
                    level=1,
                    code="missing_field",
                    field=name,
                    message=f"{name} 는 비어 있지 않은 배열이어야 합니다.",
                    hard=True,
                )
            )

    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        for index, task in enumerate(tasks):
            if not isinstance(task, dict):
                report.issues.append(
                    QualityIssue(
                        level=1,
                        code="invalid_type",
                        field=f"tasks[{index}]",
                        message="task 는 객체여야 합니다.",
                        hard=True,
                    )
                )
                continue
            for name in _TASK_TEXT_FIELDS:
                if not _is_text(task.get(name)):
                    report.issues.append(
                        QualityIssue(
                            level=1,
                            code="missing_field",
                            field=f"tasks[{index}].{name}",
                            message=f"task 의 {name} 값이 비어 있습니다.",
                            hard=True,
                        )
                    )
            tech_used = task.get("tech_used")
            if tech_used is not None and not isinstance(tech_used, list):
                report.issues.append(
                    QualityIssue(
                        level=1,
                        code="invalid_type",
                        field=f"tasks[{index}].tech_used",
                        message="tech_used 는 배열이어야 합니다.",
                        hard=False,
                    )
                )

    report.level1_ok = not report.hard_failures


def _validate_tech_stack(
    payload: dict[str, Any], evidence: EvidenceIndex, report: QualityReport
) -> None:
    tech_stack = payload.get("tech_stack")
    if not isinstance(tech_stack, list):
        return
    supported = 0
    total = 0
    unsupported: list[str] = []
    for item in tech_stack:
        if not isinstance(item, str) or not item.strip():
            continue
        total += 1
        if evidence.mentions(item.strip().lower()) or evidence.mentions(
            re.split(r"[ /]", item.strip().lower())[0]
        ):
            supported += 1
        else:
            unsupported.append(item.strip())

    report.techs_total = total
    report.techs_supported = supported

    for name in unsupported[:5]:
        report.issues.append(
            QualityIssue(
                level=2,
                code="unsupported_tech",
                field="tech_stack",
                message=f"저장소 근거에서 확인되지 않은 기술: {name}",
                hard=False,
            )
        )
    # 절반 이상이 근거 없이 등장하면 분석을 신뢰할 수 없다.
    if total and supported * 2 < total:
        report.issues.append(
            QualityIssue(
                level=2,
                code="unsupported_tech_majority",
                field="tech_stack",
                message=f"기술 스택 {total}개 중 {supported}개만 근거가 확인되었습니다.",
                hard=True,
            )
        )


def _validate_metrics(
    field_name: str, text: str, evidence: EvidenceIndex, report: QualityReport
) -> None:
    for match in _METRIC_PATTERN.finditer(text):
        number = match.group(1)
        if evidence.mentions_number(number):
            continue
        report.issues.append(
            QualityIssue(
                level=2,
                code="unverified_metric",
                field=field_name,
                message=f"저장소에서 확인되지 않은 수치: {match.group(0).strip()}",
                hard=True,
            )
        )


def _validate_level2(
    payload: dict[str, Any], evidence: EvidenceIndex, report: QualityReport
) -> None:
    _validate_tech_stack(payload, evidence, report)

    for name in _PROSE_FIELDS:
        value = payload.get(name)
        if isinstance(value, str):
            _validate_metrics(name, value, evidence, report)

    tasks = payload.get("tasks")
    seen_names: set[str] = set()
    if isinstance(tasks, list):
        for index, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            for name in ("result", "solution", "problem"):
                value = task.get(name)
                if isinstance(value, str):
                    _validate_metrics(f"tasks[{index}].{name}", value, evidence, report)
            task_name = str(task.get("name") or "").strip().lower()
            if task_name and task_name in seen_names:
                report.issues.append(
                    QualityIssue(
                        level=2,
                        code="duplicate_task",
                        field=f"tasks[{index}].name",
                        message=f"중복된 작업 이름: {task.get('name')}",
                        hard=False,
                    )
                )
            seen_names.add(task_name)

    report.level2_ok = not report.hard_failures


def validate_analysis(
    payload: Any,
    evidence: EvidenceIndex,
    *,
    review_passed: Optional[bool] = None,
) -> QualityReport:
    """AI 딥 분석 payload 를 Level 1·2 기준으로 검증한다.

    Level 3(심사) 결과는 이미 계산된 값이 있으면 `review_passed` 로 넘겨 기록만 한다.
    """
    report = QualityReport(review_passed=review_passed)
    if not isinstance(payload, dict):
        report.level1_ok = False
        report.issues.append(
            QualityIssue(
                level=1,
                code="invalid_payload",
                field="$",
                message="분석 결과가 JSON 객체가 아닙니다.",
                hard=True,
            )
        )
        return report

    _validate_level1(payload, report)
    _validate_level2(payload, evidence, report)
    return report


def merge_review(report: QualityReport, review_passed: Optional[bool]) -> QualityReport:
    """Level 3 심사 결과를 리포트에 합친다. 심사 실패는 Hard Gate 다."""
    report.review_passed = review_passed
    if review_passed is False:
        report.issues.append(
            QualityIssue(
                level=3,
                code="review_rejected",
                field="$",
                message="포트폴리오 심사(ReviewResult)를 통과하지 못했습니다.",
                hard=True,
            )
        )
    return report


def evidence_gaps(payload: dict[str, Any], evidence: EvidenceIndex) -> list[str]:
    """근거가 부족한 항목을 사람이 읽을 수 있는 문장으로 돌려준다."""
    gaps: list[str] = []
    tech_stack = payload.get("tech_stack")
    if isinstance(tech_stack, list):
        missing = [
            str(item)
            for item in tech_stack
            if isinstance(item, str)
            and item.strip()
            and not evidence.mentions(item.lower())
        ]
        if missing:
            gaps.append("근거 미확인 기술: " + ", ".join(missing[:5]))
    return gaps


def unique_issues(issues: Iterable[QualityIssue]) -> list[QualityIssue]:
    seen: set[tuple[str, str]] = set()
    result: list[QualityIssue] = []
    for issue in issues:
        key = (issue.code, issue.field)
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result

"""제출용 성과보고서 생성.

- 기간·템플릿에 맞춰 기록된 업무/성과만 모은다(없는 내용을 채우지 않는다).
- 수치는 `Metric.verified` 인 것만 본문에 쓰고, 나머지는 "확인 필요"에 모은다.
- 결과 문장에 남은 수치 주장도 근거 텍스트와 대조해 자리표시자로 바꾼다.
- 파일 생성은 기존 DevFolio ExportEngine(Markdown/PDF/DOCX)을 재사용한다.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from impactnote.core import periods
from impactnote.core.metrics import sanitize_claims
from impactnote.core.models import (
    IMPACT_CATEGORIES,
    REPORT_TEMPLATES,
    Achievement,
    Metric,
    Report,
)
from impactnote.core.service import ImpactService
from impactnote.core.store import data_dir

ACTIVITY_TYPE_LABELS = {
    "feature": "신규 개발·기능 개선",
    "incident": "장애 대응·문제 해결",
    "operations": "운영·유지보수",
    "performance": "성능 개선·자동화",
    "quality": "품질 개선",
    "security": "보안·리스크 대응",
    "request": "고객·타 부서 요청",
    "research": "기술 조사·업무 개선",
    "collaboration": "협업·지원",
    "general": "기타",
}

IMPACT_LABELS = {
    "productivity": "생산성 향상",
    "efficiency": "업무 효율화",
    "stability": "안정성 개선",
    "quality": "품질 향상",
    "cost": "비용 절감",
    "incident_prevention": "장애 예방·해결",
    "automation": "업무 자동화",
    "customer": "고객 만족도 개선",
    "schedule": "일정 준수·납기 기여",
    "risk": "리스크 감소",
    "collaboration": "조직 간 협업 기여",
    "technical": "기술적 문제 해결",
    "process": "프로세스 개선",
}

STATUS_LABELS = {
    "verified": "근거 확인됨",
    "partially_verified": "일부 근거 확인됨",
    "user_input": "사용자 입력 기반",
    "needs_review": "추가 확인 필요",
}

SECTIONS = {
    "weekly": ["주요 업무", "완료 내용", "진행 중인 내용", "문제 및 대응", "다음 계획"],
    "monthly": [
        "월간 핵심 실적",
        "주요 수행 업무",
        "성과 및 개선 효과",
        "관련 근거",
        "후속 과제",
    ],
    "quarterly": [
        "핵심 성과 요약",
        "목표 대비 실적",
        "주요 프로젝트 기여",
        "문제 해결 및 개선 성과",
        "정량·정성 결과",
        "조직 기여도",
    ],
    "half_yearly": [
        "핵심 성과 요약",
        "목표 대비 실적",
        "주요 프로젝트 기여",
        "문제 해결 및 개선 성과",
        "정량·정성 결과",
        "조직 기여도",
    ],
    "annual": [
        "주요 성과",
        "개인 기여",
        "업무 수행 과정",
        "목표 달성 내역",
        "협업 및 업무 개선",
        "성장 및 개선 과제",
    ],
    "custom": [],
}


def _bullet(text: str, indent: str = "") -> str:
    return f"{indent}- {text}"


def _achievement_lines(
    achievement: Achievement, metrics: list[Metric], sources: Iterable[str]
) -> tuple[list[str], list[str]]:
    """성과 1건을 보고서 문장으로 바꾼다. (본문, 확인 필요 수치)"""
    source_list = list(sources)
    lines: list[str] = []
    unverified: list[str] = []

    def clean(label: str, value: str) -> str:
        if not value:
            return ""
        cleaned, dropped = sanitize_claims(value, source_list)
        for item in dropped:
            unverified.append(f"{achievement.title} · {label}: {item['raw']}")
        return cleaned

    lines.append(f"**{achievement.title}**")
    categories = [
        IMPACT_LABELS.get(item, item) for item in achievement.impact_categories
    ]
    if categories:
        lines.append(f"- 구분: {', '.join(categories)}")
    lines.append(f"- 상태: {STATUS_LABELS.get(achievement.status, achievement.status)}")
    problem = clean("문제", achievement.problem)
    if problem:
        lines.append(f"- 문제/요구사항: {problem}")
    action = clean("행동", achievement.action)
    if action:
        lines.append(f"- 수행 내용: {action}")
    result = clean("결과", achievement.result)
    if result:
        lines.append(f"- 결과: {result}")
    if achievement.contribution.role:
        lines.append(f"- 본인 역할: {achievement.contribution.role}")
    if achievement.contribution.shared:
        lines.append(f"- 공동 작업: {', '.join(achievement.contribution.shared)}")
    for metric in metrics:
        if metric.verified:
            detail = " / ".join(
                part
                for part in (
                    metric.period,
                    metric.basis,
                    "근거 연결" if metric.evidence_id else "",
                )
                if part
            )
            suffix = f" ({detail})" if detail else ""
            lines.append(f"- 지표: {metric.name} {metric.value}{metric.unit}{suffix}")
        else:
            unverified.append(
                f"{achievement.title} · 지표 `{metric.name}` "
                f"{metric.value}{metric.unit} — 근거 확인 필요"
            )
    return lines, unverified


def _group_by_project(activities: Iterable) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for activity in activities:
        key = activity.project or "(프로젝트 미지정)"
        grouped.setdefault(key, []).append(
            f"{activity.title} ({activity.date}) · {ACTIVITY_TYPE_LABELS.get(activity.activity_type, activity.activity_type)}"
        )
    return grouped


def build_content(
    service: ImpactService,
    *,
    template: str,
    period_kind: str,
    reference: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    title: str = "",
    custom_sections: Optional[list[str]] = None,
    char_limit: int = 0,
) -> tuple[str, dict]:
    """보고서 Markdown 본문과 메타데이터를 만든다(저장은 호출자 책임)."""
    if template not in REPORT_TEMPLATES:
        raise ValueError(f"지원하지 않는 템플릿입니다: {template}")
    period_start, period_end = periods.resolve_period(
        period_kind, reference=reference, start=start, end=end
    )
    bundle = service.period_bundle(period_start, period_end)
    activities = bundle["activities"]
    achievements = bundle["achievements"]
    evidence = bundle["evidence"]
    metric_map = bundle["metrics"]
    settings = service.settings()

    unverified_all: list[str] = []
    achievement_blocks: list[list[str]] = []
    for achievement in achievements:
        sources = [
            achievement.title,
            achievement.problem,
            achievement.action,
            achievement.result,
            *[
                f"{evidence[item].title} {evidence[item].reference} {evidence[item].description}"
                for item in achievement.evidence_ids
                if item in evidence
            ],
            *[
                f"{activity.description} {activity.problem} {activity.action}"
                for activity in activities
                if activity.id in achievement.activity_ids
            ],
        ]
        lines, unverified = _achievement_lines(
            achievement, metric_map.get(achievement.id, []), sources
        )
        achievement_blocks.append(lines)
        unverified_all.extend(unverified)

    evidence_lines: list[str] = []
    for item in evidence.values():
        if item.id in {
            eid for achievement in achievements for eid in achievement.evidence_ids
        }:
            verified_mark = "확인" if item.verified else "미확인"
            reference = f" — {item.reference}" if item.reference else ""
            evidence_lines.append(
                f"- [{item.type}/{verified_mark}] {item.title}{reference}"
            )

    done = [item for item in activities if item.status == "done"]
    ongoing = [item for item in activities if item.status != "done"]
    goals = service.goals()
    goal_lines = [
        f"- {goal.title}: 목표 {goal.target}{goal.unit} / 실적 {goal.actual or '(미입력)'}"
        + (f" · {goal.note}" if goal.note else "")
        for goal in goals
    ]

    body: dict[str, list[str]] = {}
    if template == "weekly":
        body["주요 업무"] = [
            _bullet(f"{item.title} ({item.date})") for item in done
        ] or ["기록된 완료 업무가 없습니다."]
        body["완료 내용"] = [
            _bullet(item.description or item.action or item.title) for item in done
        ] or ["기록된 완료 내용이 없습니다."]
        body["진행 중인 내용"] = [
            _bullet(f"{item.title} — {item.description[:120]}") for item in ongoing
        ] or ["진행 중으로 기록된 업무가 없습니다."]
        body["문제 및 대응"] = [
            _bullet(f"{item.title}: {item.problem} → {item.action}")
            for item in activities
            if item.problem
        ] or ["문제/대응이 기록된 업무가 없습니다."]
        body["다음 계획"] = [
            _bullet(item.title) for item in activities if item.status == "planned"
        ] or ["계획으로 기록된 업무가 없습니다."]
    elif template == "monthly":
        body["월간 핵심 실적"] = [
            line for block in achievement_blocks for line in block
        ] or ["이 기간에 기록된 성과가 없습니다."]
        body["주요 수행 업무"] = [_bullet(item.title) for item in activities] or [
            "기록된 업무가 없습니다."
        ]
        body["성과 및 개선 효과"] = [
            _bullet(
                f"{IMPACT_LABELS.get(cat, cat)}: "
                + ", ".join(
                    item.title for item in achievements if cat in item.impact_categories
                )
            )
            for cat in IMPACT_CATEGORIES
            if any(cat in item.impact_categories for item in achievements)
        ] or ["분류된 개선 효과가 없습니다."]
        body["관련 근거"] = evidence_lines or ["연결된 근거가 없습니다."]
        body["후속 과제"] = [
            _bullet(item.title) for item in activities if item.status != "done"
        ] or ["기록된 후속 과제가 없습니다."]
    elif template in {"quarterly", "half_yearly"}:
        body["핵심 성과 요약"] = [
            _bullet(f"{item.title} ({STATUS_LABELS.get(item.status, item.status)})")
            for item in achievements[:8]
        ] or ["이 기간에 기록된 성과가 없습니다."]
        body["목표 대비 실적"] = goal_lines or ["등록된 목표/KPI 가 없습니다."]
        grouped = _group_by_project(activities)
        body["주요 프로젝트 기여"] = [
            _bullet(f"{project}: {', '.join(titles)}")
            for project, titles in grouped.items()
        ] or ["프로젝트가 지정된 업무가 없습니다."]
        body["문제 해결 및 개선 성과"] = [
            _bullet(f"{item.title}: {item.problem} → {item.action}")
            for item in achievements
            if item.problem
        ] or ["문제 해결 기록이 없습니다."]
        body["정량·정성 결과"] = [
            line for block in achievement_blocks for line in block if "지표" in line
        ] or ["근거가 확인된 정량 지표가 없습니다."]
        body["조직 기여도"] = [
            _bullet(
                f"{item.title}: {item.contribution.role or '역할 미기록'}"
                + (
                    f" / 공동: {', '.join(item.contribution.shared)}"
                    if item.contribution.shared
                    else ""
                )
            )
            for item in achievements
        ] or ["기여도가 기록된 성과가 없습니다."]
    elif template == "annual":
        body["주요 성과"] = [
            line for block in achievement_blocks for line in block
        ] or ["기록된 성과가 없습니다."]
        body["개인 기여"] = [
            _bullet(f"{item.title}: {item.contribution.role or '역할 미기록'}")
            for item in achievements
        ] or ["기여도가 기록된 성과가 없습니다."]
        body["업무 수행 과정"] = [
            _bullet(f"{item.title}: {item.action or item.description}")
            for item in activities
            if item.action or item.description
        ] or ["수행 과정이 기록된 업무가 없습니다."]
        body["목표 달성 내역"] = goal_lines or ["등록된 목표/KPI 가 없습니다."]
        body["협업 및 업무 개선"] = [
            _bullet(f"{item.title}: {', '.join(item.collaborators)}")
            for item in activities
            if item.collaborators
        ] or ["협업이 기록된 업무가 없습니다."]
        body["성장 및 개선 과제"] = [
            _bullet(item.title) for item in activities if item.status != "done"
        ] or ["기록된 개선 과제가 없습니다."]
    else:  # custom
        outline = [item.strip() for item in (custom_sections or []) if item.strip()]
        if not outline:
            outline = ["성과 요약", "주요 업무", "개선 효과", "향후 계획"]
        for section in outline:
            keywords = [
                word for word in section.replace("/", " ").split() if len(word) >= 2
            ]
            matched = [
                item.title
                for item in achievements
                if any(
                    word in (item.title + item.result + item.action + item.problem)
                    for word in keywords
                )
            ]
            body[section] = [_bullet(title) for title in matched] or [
                "해당 항목에 연결된 기록이 없습니다."
            ]

    lines: list[str] = []
    report_title = (
        title.strip() or f"{period_start} ~ {period_end} {REPORT_TEMPLATES[template]}"
    )
    lines.append(f"# {report_title}")
    lines.append("")
    lines.append(f"- 평가 기간: {period_start} ~ {period_end}")
    lines.append(f"- 작성일: {date.today().isoformat()}")
    if settings.user_name:
        lines.append(
            f"- 작성자: {settings.user_name}"
            + (f" / {settings.organization}" if settings.organization else "")
        )
    lines.append(f"- 포함 범위: 업무 {len(activities)}건, 성과 {len(achievements)}건")
    lines.append("")
    if char_limit:
        used = 0
        limited_body: dict[str, list[str]] = {}
        for section, section_lines in body.items():
            kept: list[str] = []
            for line in section_lines:
                if used + len(line) > char_limit:
                    kept.append("(글자 수 제한으로 일부 생략)")
                    break
                kept.append(line)
                used += len(line)
            limited_body[section] = kept
        body = limited_body

    for section, section_lines in body.items():
        lines.append(f"## {section}")
        lines.extend(section_lines)
        lines.append("")
    lines.append("## 근거 및 확인 상태")
    lines.append(
        f"- 확인된 성과: {sum(1 for item in achievements if item.status == 'verified')}건 / "
        f"일부 확인: {sum(1 for item in achievements if item.status == 'partially_verified')}건 / "
        f"확인 필요: {sum(1 for item in achievements if item.status in {'needs_review', 'user_input'})}건"
    )
    if unverified_all:
        lines.append("### 확인 필요 항목 (근거 없음)")
        lines.extend(_bullet(item) for item in dict.fromkeys(unverified_all))
    else:
        lines.append("- 모든 수치가 기록/근거와 대조되었습니다.")
    lines.append("")
    lines.append(
        "> 본 문서는 성과노트에 기록된 내용만으로 작성되었습니다. "
        "근거가 확인되지 않은 수치는 본문에 사용하지 않았습니다."
    )
    content = "\n".join(lines).strip() + "\n"

    meta = {
        "title": report_title,
        "period_start": period_start,
        "period_end": period_end,
        "achievement_ids": [item.id for item in achievements],
        "activity_ids": [item.id for item in activities],
        "unverified": list(dict.fromkeys(unverified_all)),
    }
    return content, meta


def export_report(service: ImpactService, report: Report, fmt: str = "md") -> Path:
    """보고서를 파일로 내보낸다(Markdown/DOCX/PDF/TXT/CSV)."""
    from devfolio.core.export_engine import ExportEngine

    output_dir = data_dir() / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = ExportEngine()
    stem = f"impactnote_{report.template}_{report.period_start}_{report.period_end}_v{report.version}"
    fmt = (fmt or "md").lower()
    if fmt == "md":
        return engine.export_markdown(report.content, stem, output_dir)
    if fmt == "docx":
        return engine.export_docx(report.content, stem, output_dir)
    if fmt == "pdf":
        return engine.export_pdf(report.content, stem, output_dir)
    if fmt == "txt":
        path = output_dir / f"{stem}.txt"
        path.write_text(report.content, encoding="utf-8")
        return path
    if fmt == "csv":
        path = output_dir / f"{stem}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["기간", "상태", "성과", "문제", "행동", "결과", "근거 수"])
            for achievement in service.achievements():
                if achievement.id not in report.achievement_ids:
                    continue
                writer.writerow(
                    [
                        f"{report.period_start}~{report.period_end}",
                        STATUS_LABELS.get(achievement.status, achievement.status),
                        achievement.title,
                        achievement.problem,
                        achievement.action,
                        achievement.result,
                        len(achievement.evidence_ids),
                    ]
                )
        return path
    raise ValueError(f"지원하지 않는 형식입니다: {fmt}")


def create_report(
    service: ImpactService,
    *,
    template: str,
    period_kind: str,
    reference: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    title: str = "",
    custom_sections: Optional[list[str]] = None,
    char_limit: int = 0,
    fmt: str = "md",
) -> Report:
    """본문 생성 → 버전 계산 → 파일 내보내기 → 제출 이력 저장."""
    content, meta = build_content(
        service,
        template=template,
        period_kind=period_kind,
        reference=reference,
        start=start,
        end=end,
        title=title,
        custom_sections=custom_sections,
        char_limit=char_limit,
    )
    previous = [
        item
        for item in service.reports()
        if item.template == template
        and item.period_start == meta["period_start"]
        and item.period_end == meta["period_end"]
        and item.title == meta["title"]
    ]
    version = max((item.version for item in previous), default=0) + 1
    report = Report(
        title=meta["title"],
        template=template,
        period_kind=period_kind,
        period_start=meta["period_start"],
        period_end=meta["period_end"],
        achievement_ids=meta["achievement_ids"],
        activity_ids=meta["activity_ids"],
        content=content,
        format=fmt,
        version=version,
    )
    try:
        path = export_report(service, report, fmt)
        report.file_name = path.name
    except Exception as exc:  # noqa: BLE001 — 파일 실패해도 본문/이력은 남긴다
        report.note = f"파일 생성 실패: {type(exc).__name__}"
    return service.save_report(report)


__all__ = [
    "ACTIVITY_TYPE_LABELS",
    "IMPACT_LABELS",
    "SECTIONS",
    "build_content",
    "create_report",
    "export_report",
]

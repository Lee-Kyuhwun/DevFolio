"""기간 계산·집계 — 보고서에 들어갈 업무와 성과를 정확히 고른다."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Iterable, Optional

from impactnote.core.models import Activity, Achievement


def _parse(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def resolve_period(
    kind: str,
    *,
    reference: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> tuple[str, str]:
    """기간 종류를 (시작일, 종료일) 로 바꾼다.

    종류: custom | week | month | quarter | half | year
    기준일(reference)은 해당 기간 안의 아무 날짜나 가능하다(기본: 오늘).
    """
    ref = _parse(reference) if reference else date.today()
    if ref is None:
        ref = date.today()

    if kind == "custom":
        first = _parse(start or "") or ref
        last = _parse(end or "") or first
        if last < first:
            first, last = last, first
        return first.isoformat(), last.isoformat()

    if kind == "week":
        first = ref - timedelta(days=ref.weekday())
        return first.isoformat(), (first + timedelta(days=6)).isoformat()
    if kind == "month":
        last_day = calendar.monthrange(ref.year, ref.month)[1]
        return (
            date(ref.year, ref.month, 1).isoformat(),
            date(ref.year, ref.month, last_day).isoformat(),
        )
    if kind == "quarter":
        first_month = ((ref.month - 1) // 3) * 3 + 1
        last_month = first_month + 2
        last_day = calendar.monthrange(ref.year, last_month)[1]
        return (
            date(ref.year, first_month, 1).isoformat(),
            date(ref.year, last_month, last_day).isoformat(),
        )
    if kind == "half":
        first_month, last_month = (1, 6) if ref.month <= 6 else (7, 12)
        last_day = calendar.monthrange(ref.year, last_month)[1]
        return (
            date(ref.year, first_month, 1).isoformat(),
            date(ref.year, last_month, last_day).isoformat(),
        )
    if kind == "year":
        return date(ref.year, 1, 1).isoformat(), date(ref.year, 12, 31).isoformat()

    raise ValueError(f"지원하지 않는 기간 종류입니다: {kind}")


def overlaps(start: str, end: str, period_start: str, period_end: str) -> bool:
    return start <= period_end and end >= period_start


def activity_range(activity: Activity) -> tuple[str, str]:
    return activity.date, activity.period_end or activity.date


def achievement_range(
    achievement: Achievement, activities: Iterable[Activity]
) -> tuple[str, str]:
    """성과 기간 — 명시값 우선, 없으면 연결된 활동 기간의 합집합."""
    if achievement.period_start:
        return (
            achievement.period_start,
            achievement.period_end or achievement.period_start,
        )
    linked = {activity.id: activity for activity in activities}
    dates: list[tuple[str, str]] = [
        activity_range(linked[item_id])
        for item_id in achievement.activity_ids
        if item_id in linked
    ]
    if dates:
        return min(item[0] for item in dates), max(item[1] for item in dates)
    created = achievement.created_at[:10]
    return created, created


def select_activities(
    activities: Iterable[Activity], start: str, end: str
) -> list[Activity]:
    selected = [
        activity
        for activity in activities
        if overlaps(*activity_range(activity), start, end)
    ]
    return sorted(selected, key=lambda item: (item.date, item.created_at), reverse=True)


def select_achievements(
    achievements: Iterable[Achievement],
    activities: list[Activity],
    start: str,
    end: str,
) -> list[Achievement]:
    selected = []
    for achievement in achievements:
        period_start, period_end = achievement_range(achievement, activities)
        if overlaps(period_start, period_end, start, end):
            selected.append(achievement)
    order = {"verified": 0, "partially_verified": 1, "user_input": 2, "needs_review": 3}
    return sorted(
        selected,
        key=lambda item: (order.get(item.status, 9), item.updated_at),
    )


__all__ = [
    "achievement_range",
    "activity_range",
    "overlaps",
    "resolve_period",
    "select_activities",
    "select_achievements",
]

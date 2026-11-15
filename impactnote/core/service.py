"""성과노트 서비스 계층 — CRUD·상태 계산·기간 집계.

라우터와 CLI 는 이 서비스만 호출한다(저장 형식·검증 규칙이 한 곳에 모이게).
"""

from __future__ import annotations

from typing import Iterable, Optional

from impactnote.core import periods
from impactnote.core.metrics import metric_is_verified
from impactnote.core.models import (
    ACHIEVEMENT_STATUSES,
    Activity,
    Achievement,
    AIAnalysis,
    Contribution,
    Evidence,
    Goal,
    Metric,
    Report,
    Settings,
)
from impactnote.core.models import utc_now
from impactnote.core.store import JsonStore, get_store


class NotFound(Exception):
    pass


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


class ImpactService:
    def __init__(self, store: Optional[JsonStore] = None) -> None:
        self.store = store or get_store()

    # ------------------------------------------------------------------
    # 업무 활동
    # ------------------------------------------------------------------
    def activities(self) -> list[Activity]:
        items = self.store.all("activities", Activity)
        return sorted(
            items, key=lambda item: (item.date, item.created_at), reverse=True
        )

    def activity(self, activity_id: str) -> Activity:
        item = self.store.get("activities", activity_id, Activity)
        if item is None:
            raise NotFound("업무 기록을 찾을 수 없습니다.")
        return item

    def create_activity(self, payload: dict) -> Activity:
        activity = Activity.model_validate(payload)
        self.store.put("activities", activity)
        return activity

    def update_activity(self, activity_id: str, payload: dict) -> Activity:
        current = self.activity(activity_id)
        merged = {**current.model_dump(mode="json"), **payload, "id": activity_id}
        merged["updated_at"] = utc_now()
        activity = Activity.model_validate(merged)
        self.store.put("activities", activity)
        return activity

    def delete_activity(self, activity_id: str) -> bool:
        deleted = self.store.delete("activities", activity_id)
        if deleted:
            # 참조 무결성: 성과에서 사라진 활동 ID 를 제거한다.
            for achievement in self.achievements():
                if activity_id in achievement.activity_ids:
                    achievement.activity_ids = [
                        item for item in achievement.activity_ids if item != activity_id
                    ]
                    achievement.updated_at = utc_now()
                    self.store.put("achievements", achievement)
        return deleted

    # ------------------------------------------------------------------
    # 근거
    # ------------------------------------------------------------------
    def evidence(self) -> list[Evidence]:
        items = self.store.all("evidence", Evidence)
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def evidence_map(self) -> dict[str, Evidence]:
        return {item.id: item for item in self.evidence()}

    def create_evidence(self, payload: dict) -> Evidence:
        evidence = Evidence.model_validate(payload)
        self.store.put("evidence", evidence)
        return evidence

    def update_evidence(self, evidence_id: str, payload: dict) -> Evidence:
        current = self._get_evidence(evidence_id)
        merged = {**current.model_dump(mode="json"), **payload, "id": evidence_id}
        evidence = Evidence.model_validate(merged)
        self.store.put("evidence", evidence)
        self.refresh_achievement_statuses()
        return evidence

    def delete_evidence(self, evidence_id: str) -> bool:
        deleted = self.store.delete("evidence", evidence_id)
        if deleted:
            for achievement in self.achievements():
                if evidence_id in achievement.evidence_ids:
                    achievement.evidence_ids = [
                        item for item in achievement.evidence_ids if item != evidence_id
                    ]
                    self._apply_status(achievement)
                    self.store.put("achievements", achievement)
            for activity in self.activities():
                if evidence_id in activity.evidence_ids:
                    activity.evidence_ids = [
                        item for item in activity.evidence_ids if item != evidence_id
                    ]
                    self.store.put("activities", activity)
            for metric in self.metrics():
                if metric.evidence_id == evidence_id:
                    metric.verified = False
                    self.store.put("metrics", metric)
        return deleted

    def _get_evidence(self, evidence_id: str) -> Evidence:
        item = self.store.get("evidence", evidence_id, Evidence)
        if item is None:
            raise NotFound("근거 자료를 찾을 수 없습니다.")
        return item

    # ------------------------------------------------------------------
    # 성과
    # ------------------------------------------------------------------
    def achievements(self) -> list[Achievement]:
        items = self.store.all("achievements", Achievement)
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def achievement(self, achievement_id: str) -> Achievement:
        item = self.store.get("achievements", achievement_id, Achievement)
        if item is None:
            raise NotFound("성과를 찾을 수 없습니다.")
        return item

    def create_achievement(self, payload: dict) -> Achievement:
        achievement = Achievement.model_validate(payload)
        self._apply_status(achievement)
        self.store.put("achievements", achievement)
        return achievement

    def update_achievement(self, achievement_id: str, payload: dict) -> Achievement:
        current = self.achievement(achievement_id)
        merged = {
            **current.model_dump(mode="json"),
            **payload,
            "id": achievement_id,
            "updated_at": utc_now(),
        }
        achievement = Achievement.model_validate(merged)
        self._apply_status(achievement)
        self.store.put("achievements", achievement)
        return achievement

    def delete_achievement(self, achievement_id: str) -> bool:
        deleted = self.store.delete("achievements", achievement_id)
        if deleted:
            for metric in self.metrics():
                if metric.achievement_id == achievement_id:
                    self.store.delete("metrics", metric.id)
        return deleted

    def create_achievement_from_activities(
        self, activity_ids: list[str], *, title: str = ""
    ) -> Achievement:
        """선택한 업무 기록을 하나의 성과로 묶는다(수치는 사용자가 확인 후 입력)."""
        activities = [self.activity(item) for item in activity_ids]
        if not activities:
            raise NotFound("성과로 만들 업무 기록이 없습니다.")
        dates = [item.date for item in activities]
        evidence_ids = _unique(
            evidence for activity in activities for evidence in activity.evidence_ids
        )
        payload = {
            "title": title.strip() or activities[0].title,
            "activity_ids": [item.id for item in activities],
            "problem": next((item.problem for item in activities if item.problem), ""),
            "action": next((item.action for item in activities if item.action), "")
            or activities[0].description,
            "result": "",
            "impact_categories": [],
            "evidence_ids": evidence_ids,
            "period_start": min(dates),
            "period_end": max(dates),
            "source": "manual",
        }
        return self.create_achievement(payload)

    def _apply_status(self, achievement: Achievement) -> None:
        evidence = self.evidence_map()
        linked = [
            evidence[item] for item in achievement.evidence_ids if item in evidence
        ]
        # AI·Git 이 만든 후보는 사용자가 확인하기 전까지 "근거 확인됨"으로 올리지 않는다.
        if achievement.source in {"ai", "git"} and not achievement.confirmed:
            achievement.status = "needs_review"
            achievement.needs_review = True
            return
        if linked and all(item.verified for item in linked):
            achievement.status = "verified"
            achievement.needs_review = False
        elif any(item.verified for item in linked):
            achievement.status = "partially_verified"
            achievement.needs_review = True
        elif linked or achievement.needs_review:
            achievement.status = "needs_review"
            achievement.needs_review = True
        else:
            achievement.status = "user_input"

    def refresh_achievement_statuses(self) -> None:
        for achievement in self.achievements():
            self._apply_status(achievement)
            self.store.put("achievements", achievement)

    def link_evidence(
        self,
        achievement_id: str,
        evidence_ids: list[str],
    ) -> Achievement:
        """근거를 연결한다. 미확인 근거도 연결은 하되 상태를 verified 로 올리지 않는다."""
        achievement = self.achievement(achievement_id)
        items = [self._get_evidence(item) for item in _unique(evidence_ids)]
        achievement.evidence_ids = _unique(
            [*achievement.evidence_ids, *(item.id for item in items)]
        )
        achievement.updated_at = utc_now()
        self._apply_status(achievement)
        self.store.put("achievements", achievement)
        return achievement

    # ------------------------------------------------------------------
    # 지표
    # ------------------------------------------------------------------
    def metrics(self) -> list[Metric]:
        return self.store.all("metrics", Metric)

    def add_metric(self, achievement_id: str, payload: dict) -> Metric:
        achievement = self.achievement(achievement_id)
        payload = {**payload, "achievement_id": achievement_id}
        metric = Metric.model_validate(payload)
        sources = self._sources_for(achievement) + [metric.basis]
        metric.verified = metric.verified and metric_is_verified(
            metric.value,
            metric.unit,
            sources,
            evidence_id=metric.evidence_id,
            basis=metric.basis,
        )
        self.store.put("metrics", metric)
        return metric

    def delete_metric(self, metric_id: str) -> bool:
        return self.store.delete("metrics", metric_id)

    def _sources_for(self, achievement: Achievement) -> list[str]:
        evidence = self.evidence_map()
        texts = [
            achievement.problem,
            achievement.action,
            achievement.result,
            achievement.title,
        ]
        texts.extend(
            evidence[item].description + " " + evidence[item].title
            for item in achievement.evidence_ids
            if item in evidence
        )
        texts.extend(
            activity.description + " " + activity.problem + " " + activity.action
            for activity in self.activities()
            if activity.id in achievement.activity_ids
        )
        return texts

    # ------------------------------------------------------------------
    # 기간 집계·대시보드
    # ------------------------------------------------------------------
    def period_bundle(
        self,
        start: str,
        end: str,
        *,
        include_unverified: bool = True,
    ) -> dict:
        activities = periods.select_activities(self.activities(), start, end)
        achievements = periods.select_achievements(
            self.achievements(), self.activities(), start, end
        )
        if not include_unverified:
            achievements = [
                item for item in achievements if item.status != "needs_review"
            ]
        evidence = self.evidence_map()
        metric_map: dict[str, list[Metric]] = {}
        for metric in self.metrics():
            metric_map.setdefault(metric.achievement_id, []).append(metric)
        return {
            "start": start,
            "end": end,
            "activities": activities,
            "achievements": achievements,
            "evidence": evidence,
            "metrics": metric_map,
        }

    def dashboard(self) -> dict:
        from datetime import date

        today = date.today().isoformat()
        week_start, week_end = periods.resolve_period("week", reference=today)
        month_start, month_end = periods.resolve_period("month", reference=today)
        quarter_start, quarter_end = periods.resolve_period("quarter", reference=today)

        achievements = self.achievements()
        report_list = self.reports()
        return {
            "week": self.period_bundle(week_start, week_end),
            "month": self.period_bundle(month_start, month_end),
            "quarter": self.period_bundle(quarter_start, quarter_end),
            "counts": {
                "verified": sum(
                    1 for item in achievements if item.status == "verified"
                ),
                "partially_verified": sum(
                    1 for item in achievements if item.status == "partially_verified"
                ),
                "needs_review": sum(
                    1
                    for item in achievements
                    if item.status in {"needs_review", "user_input"}
                ),
            },
            "in_progress": [
                activity for activity in self.activities() if activity.status != "done"
            ][:5],
            "recent_reports": report_list[:3],
        }

    # ------------------------------------------------------------------
    # 보고서
    # ------------------------------------------------------------------
    def reports(self) -> list[Report]:
        items = self.store.all("reports", Report)
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def report(self, report_id: str) -> Report:
        item = self.store.get("reports", report_id, Report)
        if item is None:
            raise NotFound("보고서를 찾을 수 없습니다.")
        return item

    def save_report(self, report: Report) -> Report:
        self.store.put("reports", report)
        return report

    # ------------------------------------------------------------------
    # 목표·설정·분석
    # ------------------------------------------------------------------
    def goals(self) -> list[Goal]:
        return self.store.all("goals", Goal)

    def create_goal(self, payload: dict) -> Goal:
        goal = Goal.model_validate(payload)
        self.store.put("goals", goal)
        return goal

    def settings(self) -> Settings:
        return self.store.settings()

    def save_settings(self, payload: dict) -> Settings:
        current = self.store.settings().model_dump(mode="json")
        merged = {**current, **payload, "updated_at": utc_now()}
        settings = Settings.model_validate(merged)
        self.store.save_settings(settings)
        return settings

    def analyses(self) -> list[AIAnalysis]:
        items = self.store.all("analyses", AIAnalysis)
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def save_analysis(self, analysis: AIAnalysis) -> AIAnalysis:
        self.store.put("analyses", analysis)
        return analysis

    def apply_analysis(self, analysis_id: str) -> Achievement:
        """AI가 제안한 성과 후보를 성과로 저장한다(원본 기록은 그대로 둔다)."""
        analysis = self.store.get("analyses", analysis_id, AIAnalysis)
        if analysis is None:
            raise NotFound("AI 분석 결과를 찾을 수 없습니다.")
        if analysis.status != "completed":
            raise ValueError("실패한 분석은 성과로 적용할 수 없습니다.")
        result = analysis.result or {}
        contribution_payload = result.get("contribution") or {}
        achievement = Achievement(
            title=str(result.get("title") or "AI 성과 후보")[:200],
            activity_ids=[analysis.activity_id] if analysis.activity_id else [],
            problem=str(result.get("problem", ""))[:3000],
            action=str(result.get("action", ""))[:3000],
            result=str(result.get("result", ""))[:3000],
            impact_categories=list(result.get("impact_categories") or []),
            contribution=Contribution.model_validate(
                {
                    key: value
                    for key, value in contribution_payload.items()
                    if key in Contribution.model_fields
                }
            )
            if isinstance(contribution_payload, dict)
            else Contribution(),
            status="needs_review",
            needs_review=True,
            source="ai",
        )
        self.store.put("achievements", achievement)
        analysis.applied_achievement_id = achievement.id
        self.save_analysis(analysis)
        return achievement


__all__ = ["ACHIEVEMENT_STATUSES", "ImpactService", "NotFound"]

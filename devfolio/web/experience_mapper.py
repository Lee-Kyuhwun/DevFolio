"""웹 Experience DTO 와 기존 ProjectDraft/Project 간 매핑."""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

from devfolio.models.draft import ExperienceDraft, ExperienceSummary, ProjectDraft
from devfolio.models.project import (
    ProjectLinks,
    ProjectStudioMeta,
    StudioExtraLink,
    default_studio_meta_payload,
    derive_experience_kind,
)

_PROJECT_TYPE_BY_EXPERIENCE_KIND = {
    "work": "company",
    "personal": "side",
    "study": "course",
    "toy": "side",
}

_DOC_TYPES = ("resume", "career", "portfolio")
_EXPERIENCE_KINDS = ("work", "personal", "study", "toy")


def project_type_for_experience_kind(experience_kind: str) -> str:
    return _PROJECT_TYPE_BY_EXPERIENCE_KIND.get(experience_kind, "company")


def _link_kind_from_url(url: str) -> str | None:
    host = urlparse(url.strip()).netloc.lower()
    if not host:
        return None
    if "github.com" in host:
        return "github"
    if any(domain in host for domain in ("youtube.com", "youtu.be", "vimeo.com", "loom.com")):
        return "video"
    if any(domain in host for domain in ("readme.com", "notion.site", "notion.so", "gitbook.io", "docs.")):
        return "docs"
    if host:
        return "demo"
    return None


def sync_canonical_links(links: ProjectLinks, extra_links: Iterable[StudioExtraLink]) -> ProjectLinks:
    updated = links.model_copy(deep=True)
    for item in extra_links:
        url = (item.url or "").strip()
        if not url:
            continue
        kind = _link_kind_from_url(url)
        if kind and not getattr(updated, kind):
            setattr(updated, kind, url)
    return updated


def experience_from_project_draft(draft: ProjectDraft) -> ExperienceDraft:
    experience_kind = draft.studio_meta.experience_kind or derive_experience_kind(draft.type)
    studio_meta = draft.studio_meta.model_copy(
        update={
            "experience_kind": experience_kind,
            "collaboration": draft.studio_meta.collaboration or draft.team_size > 1,
        }
    )
    return ExperienceDraft(
        id=draft.id,
        title=draft.name,
        type=experience_kind,
        status=draft.status,
        organization=draft.organization,
        period=draft.period.model_copy(deep=True),
        role=draft.role,
        team_size=draft.team_size,
        tech_stack=list(draft.tech_stack),
        one_line_summary=draft.one_line_summary,
        summary=draft.summary,
        links=draft.links.model_copy(deep=True),
        overview=draft.overview.model_copy(deep=True),
        user_flow=[step.model_copy(deep=True) for step in draft.user_flow],
        tech_stack_detail=draft.tech_stack_detail.model_copy(deep=True),
        architecture=draft.architecture.model_copy(deep=True),
        features=[feature.model_copy(deep=True) for feature in draft.features],
        problem_solving_cases=[case.model_copy(deep=True) for case in draft.problem_solving_cases],
        performance_security_operations=draft.performance_security_operations.model_copy(deep=True),
        results=draft.results.model_copy(deep=True),
        retrospective=draft.retrospective.model_copy(deep=True),
        assets=draft.assets.model_copy(deep=True),
        studio_meta=studio_meta,
        tags=list(draft.tags),
        tasks=[task.model_copy(deep=True) for task in draft.tasks],
        raw_text=draft.raw_text,
    )


def project_draft_from_experience(experience: ExperienceDraft) -> ProjectDraft:
    base_studio_meta = experience.studio_meta.model_copy(
        update={
            "experience_kind": experience.type,
            "collaboration": experience.studio_meta.collaboration or experience.team_size > 1,
        }
    )
    synced_links = sync_canonical_links(experience.links, base_studio_meta.extra_links)
    return ProjectDraft(
        id=experience.id,
        name=experience.title,
        type=project_type_for_experience_kind(experience.type),
        status=experience.status,
        organization=experience.organization,
        period=experience.period.model_copy(deep=True),
        role=experience.role,
        team_size=experience.team_size,
        tech_stack=list(experience.tech_stack),
        one_line_summary=experience.one_line_summary,
        summary=experience.summary,
        links=synced_links,
        overview=experience.overview.model_copy(deep=True),
        user_flow=[step.model_copy(deep=True) for step in experience.user_flow],
        tech_stack_detail=experience.tech_stack_detail.model_copy(deep=True),
        architecture=experience.architecture.model_copy(deep=True),
        features=[feature.model_copy(deep=True) for feature in experience.features],
        problem_solving_cases=[case.model_copy(deep=True) for case in experience.problem_solving_cases],
        performance_security_operations=experience.performance_security_operations.model_copy(deep=True),
        results=experience.results.model_copy(deep=True),
        retrospective=experience.retrospective.model_copy(deep=True),
        assets=experience.assets.model_copy(deep=True),
        studio_meta=base_studio_meta,
        tags=list(experience.tags),
        tasks=[task.model_copy(deep=True) for task in experience.tasks],
        raw_text=experience.raw_text,
    )


def ensure_project_studio_meta(draft: ProjectDraft) -> ProjectDraft:
    if draft.studio_meta:
        return draft
    return draft.model_copy(
        update={
            "studio_meta": ProjectStudioMeta.model_validate(
                default_studio_meta_payload(draft.type, draft.team_size)
            )
        }
    )


def summarize_experiences(experiences: list[ExperienceDraft]) -> ExperienceSummary:
    by_type = {kind: 0 for kind in _EXPERIENCE_KINDS}
    by_document = {doc_type: 0 for doc_type in _DOC_TYPES}
    for experience in experiences:
        by_type[experience.type] = by_type.get(experience.type, 0) + 1
        for doc_type in experience.studio_meta.document_targets:
            by_document[doc_type] = by_document.get(doc_type, 0) + 1
    return ExperienceSummary(
        total=len(experiences),
        by_type=by_type,
        by_document=by_document,
    )

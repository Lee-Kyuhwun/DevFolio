"""프로젝트 및 작업 내역 CRUD 관리자."""

from __future__ import annotations

import uuid
from typing import Optional

from devfolio.core.storage import (
    delete_project_file,
    find_project_by_name,
    list_projects,
    project_id_from_name,
    save_project,
)
from devfolio.exceptions import (
    DevfolioError,
    DevfolioProjectNotFoundError,
    DevfolioTaskNotFoundError,
)
from devfolio.models.draft import ProjectDraft
from devfolio.models.project import Period, Project, Task


class ProjectManager:
    @staticmethod
    def _clean_string_list(values: Optional[list[str]]) -> list[str]:
        return [value.strip() for value in (values or []) if value and value.strip()]

    @staticmethod
    def _next_task_id(used_ids: Optional[set[str]] = None) -> str:
        used = used_ids or set()
        while True:
            candidate = f"task_{uuid.uuid4().hex[:8]}"
            if candidate not in used:
                return candidate

    def _next_project_id(self, name: str, exclude_project_id: Optional[str] = None) -> str:
        """프로젝트명으로 고유 ID 생성.

        - 정확히 같은 이름이 이미 있으면 명시적 오류
        - 정규화 충돌은 suffix(_2, _3, ...)로 해소
        """
        projects = list_projects()

        for project in projects:
            if project.id != exclude_project_id and project.name == name:
                raise DevfolioError(
                    f"이미 같은 이름의 프로젝트가 있습니다: '{name}'",
                    hint="`devfolio project list`로 기존 프로젝트를 확인하세요.",
                )

        base_id = project_id_from_name(name)
        used_ids = {project.id for project in projects if project.id != exclude_project_id}

        if base_id not in used_ids:
            return base_id

        for index in range(2, 100):
            candidate = f"{base_id}_{index}"
            if candidate not in used_ids:
                return candidate

        raise DevfolioError(
            f"프로젝트 ID를 생성할 수 없습니다: '{name}'",
            hint="프로젝트명을 더 구체적으로 지정하세요.",
        )

    def draft_from_project(self, project: Project) -> ProjectDraft:
        """저장된 Project를 웹 편집용 Draft로 변환한다."""
        return ProjectDraft.model_validate(project.model_dump())

    def project_from_draft(
        self,
        draft: ProjectDraft,
        project_id: Optional[str] = None,
        *,
        transient: bool = False,
    ) -> Project:
        """Draft를 Project 모델로 변환한다.

        transient=True인 경우 저장하지 않는 미리보기용 Project를 생성한다.
        """
        project_name = (draft.name or "").strip() or ("Untitled Project" if transient else "")
        if not project_name:
            raise DevfolioError(
                "프로젝트명은 비워둘 수 없습니다.",
                hint="초안 검토 단계에서 프로젝트명을 먼저 입력하세요.",
            )

        resolved_id = (project_id or draft.id or "").strip()
        if not resolved_id:
            base_name = draft.name.strip() if draft.name.strip() else "draft_project"
            resolved_id = project_id_from_name(base_name)

        used_task_ids: set[str] = set()
        tasks: list[Task] = []
        for task_draft in draft.tasks:
            task_name = (task_draft.name or "").strip() or "Untitled Task"
            task_id = (task_draft.id or "").strip()
            if not task_id or task_id in used_task_ids:
                task_id = self._next_task_id(used_task_ids)
            used_task_ids.add(task_id)

            tasks.append(
                Task(
                    id=task_id,
                    name=task_name,
                    period=Period.model_validate(task_draft.period.model_dump(exclude_none=False)),
                    problem=task_draft.problem,
                    solution=task_draft.solution,
                    result=task_draft.result,
                    tech_used=self._clean_string_list(task_draft.tech_used),
                    keywords=self._clean_string_list(task_draft.keywords),
                    ai_generated_text=task_draft.ai_generated_text,
                )
            )

        return Project(
            id=resolved_id,
            name=project_name,
            type=draft.type,
            status=draft.status,
            organization=draft.organization,
            period=Period.model_validate(draft.period.model_dump(exclude_none=False)),
            role=draft.role,
            team_size=draft.team_size,
            tech_stack=self._clean_string_list(draft.tech_stack),
            summary=draft.summary,
            tags=self._clean_string_list(draft.tags),
            tasks=tasks,
        )

    def save_project_draft(
        self,
        draft: ProjectDraft,
        project_id: Optional[str] = None,
    ) -> Project:
        """웹 편집 초안을 실제 Project로 저장한다."""
        draft_name = (draft.name or "").strip()
        if not draft_name:
            raise DevfolioError(
                "프로젝트명은 비워둘 수 없습니다.",
                hint="초안 검토 단계에서 프로젝트명을 먼저 입력하세요.",
            )

        target = self.get_project_or_raise(project_id) if project_id else None
        if target is None:
            project = self.project_from_draft(
                draft,
                project_id=self._next_project_id(draft_name),
            )
            save_project(project)
            return project

        updated_project = self.project_from_draft(
            draft,
            project_id=target.id,
        )
        return self.rename_project(
            target.id,
            new_name=updated_project.name,
            type=updated_project.type,
            status=updated_project.status,
            organization=updated_project.organization,
            period=updated_project.period,
            role=updated_project.role,
            team_size=updated_project.team_size,
            tech_stack=updated_project.tech_stack,
            summary=updated_project.summary,
            tags=updated_project.tags,
            tasks=updated_project.tasks,
        )

    def save_project_summary(self, name_or_id: str, summary: str) -> Project:
        """프로젝트 요약을 저장한다."""
        return self.update_project(name_or_id, summary=summary)

    # ------------------------------------------------------------------
    # 프로젝트
    # ------------------------------------------------------------------

    def create_project(
        self,
        name: str,
        type: str = "company",
        status: str = "done",
        organization: str = "",
        period_start: str = "",
        period_end: Optional[str] = None,
        role: str = "",
        team_size: int = 1,
        tech_stack: Optional[list[str]] = None,
        summary: str = "",
        tags: Optional[list[str]] = None,
    ) -> Project:
        """새 프로젝트를 생성하고 저장한다."""
        project_id = self._next_project_id(name)

        project = Project(
            id=project_id,
            name=name,
            type=type,
            status=status,
            organization=organization,
            period=Period(start=period_start or None, end=period_end or None),
            role=role,
            team_size=team_size,
            tech_stack=tech_stack or [],
            summary=summary,
            tags=tags or [],
            tasks=[],
        )
        save_project(project)
        return project

    def get_project(self, name_or_id: str) -> Optional[Project]:
        """이름 또는 ID로 프로젝트 검색. 없으면 None."""
        return find_project_by_name(name_or_id)

    def get_project_or_raise(self, name_or_id: str) -> Project:
        """이름 또는 ID로 프로젝트 검색. 없으면 DevfolioProjectNotFoundError."""
        project = find_project_by_name(name_or_id)
        if not project:
            raise DevfolioProjectNotFoundError(name_or_id)
        return project

    def update_project(self, name_or_id: str, **kwargs) -> Project:
        """프로젝트 필드를 업데이트한다."""
        project = self.get_project_or_raise(name_or_id)
        updated = project.model_copy(update={k: v for k, v in kwargs.items() if v is not None})
        save_project(updated)
        return updated

    def rename_project(self, name_or_id: str, new_name: str, **kwargs) -> Project:
        """프로젝트명을 변경하고 필드를 업데이트한다. ID 충돌 시 자동 suffix 부여."""
        project = self.get_project_or_raise(name_or_id)

        updates = {k: v for k, v in kwargs.items() if v is not None}
        if new_name != project.name:
            updates["name"] = new_name
            updates["id"] = self._next_project_id(new_name, exclude_project_id=project.id)
        else:
            updates["name"] = project.name
            updates["id"] = project.id

        updated = project.model_copy(update=updates)
        save_project(updated)
        if updated.id != project.id:
            delete_project_file(project.id)
        return updated

    def delete_project(self, name_or_id: str) -> bool:
        """프로젝트를 삭제한다. 없으면 DevfolioProjectNotFoundError."""
        project = self.get_project_or_raise(name_or_id)
        return delete_project_file(project.id)

    def list_projects(
        self,
        stack_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
    ) -> list[Project]:
        projects = list_projects()
        if stack_filter:
            sf = stack_filter.lower()
            projects = [p for p in projects if any(sf in s.lower() for s in p.tech_stack)]
        if type_filter:
            projects = [p for p in projects if p.type == type_filter]
        if tag_filter:
            tf = tag_filter.lower()
            projects = [p for p in projects if any(tf in t.lower() for t in p.tags)]
        return projects

    # ------------------------------------------------------------------
    # 작업 내역 (Task)
    # ------------------------------------------------------------------

    def add_task(
        self,
        project_name: str,
        name: str,
        period_start: str = "",
        period_end: Optional[str] = None,
        problem: str = "",
        solution: str = "",
        result: str = "",
        tech_used: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
    ) -> Task:
        """프로젝트에 작업 내역을 추가한다."""
        project = self.get_project_or_raise(project_name)
        task = Task(
            id=self._next_task_id({t.id for t in project.tasks}),
            name=name,
            period=Period(start=period_start or None, end=period_end or None),
            problem=problem,
            solution=solution,
            result=result,
            tech_used=tech_used or [],
            keywords=keywords or [],
        )
        project.tasks.append(task)
        save_project(project)
        return task

    def _find_task(self, project: Project, task_name: str) -> Task:
        task = next(
            (t for t in project.tasks if t.name == task_name or t.id == task_name),
            None,
        )
        if not task:
            raise DevfolioTaskNotFoundError(task_name, project.name)
        return task

    def get_task_or_raise(self, project_name: str, task_name: str) -> tuple[Project, Task]:
        project = self.get_project_or_raise(project_name)
        task = self._find_task(project, task_name)
        return project, task

    def update_task(self, project_name: str, task_name: str, **kwargs) -> Task:
        """작업 내역을 수정한다. 내용 변경 시 AI 캐시를 무효화."""
        project, task = self.get_task_or_raise(project_name, task_name)

        # 내용 변경 시 AI 캐시 무효화
        content_fields = {"problem", "solution", "result", "tech_used", "name"}
        invalidate_cache = bool(content_fields & set(kwargs.keys()))

        updates = {k: v for k, v in kwargs.items() if v is not None}
        if invalidate_cache:
            updates["ai_generated_text"] = ""

        updated_task = task.model_copy(update=updates)
        project.tasks = [
            updated_task if t.id == task.id else t for t in project.tasks
        ]
        save_project(project)
        return updated_task

    def delete_task(self, project_name: str, task_name: str) -> bool:
        """작업 내역을 삭제한다. 없으면 False."""
        project = self.get_project_or_raise(project_name)
        task = next(
            (t for t in project.tasks if t.name == task_name or t.id == task_name),
            None,
        )
        if not task:
            return False
        project.tasks = [t for t in project.tasks if t.id != task.id]
        save_project(project)
        return True

    def save_task_ai_text(
        self, project_name: str, task_name: str, ai_text: str
    ) -> bool:
        """AI 생성 문구를 작업 내역에 캐싱."""
        try:
            project, task = self.get_task_or_raise(project_name, task_name)
            updated_task = task.model_copy(update={"ai_generated_text": ai_text})
            project.tasks = [
                updated_task if t.id == task.id else t for t in project.tasks
            ]
            save_project(project)
            return True
        except Exception:
            return False

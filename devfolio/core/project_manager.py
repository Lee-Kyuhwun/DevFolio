"""프로젝트 및 작업 내역 CRUD 관리자."""

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
from devfolio.models.project import Period, Project, Task


class ProjectManager:
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
        return find_project_by_name(name_or_id)

    def get_project_or_raise(self, name_or_id: str) -> Project:
        project = find_project_by_name(name_or_id)
        if not project:
            raise DevfolioProjectNotFoundError(name_or_id)
        return project

    def update_project(self, name_or_id: str, **kwargs) -> Project:
        project = self.get_project_or_raise(name_or_id)
        updated = project.model_copy(update={k: v for k, v in kwargs.items() if v is not None})
        save_project(updated)
        return updated

    def rename_project(self, name_or_id: str, new_name: str, **kwargs) -> Project:
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
        project = self.get_project_or_raise(project_name)
        task = Task(
            id=f"task_{uuid.uuid4().hex[:8]}",
            name=name,
            period=Period(start=period_start, end=period_end),
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
        project = self.get_project_or_raise(project_name)
        # raise 없이 직접 확인
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

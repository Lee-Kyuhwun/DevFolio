"""프로젝트 및 작업 내역 CRUD 관리자.

[Spring 비교]
  @Service 클래스 — Repository(storage.py) 위에 비즈니스 로직을 얹은 서비스 계층.
  storage.py 가 데이터 접근(DAO) 역할이라면, ProjectManager 는 @Service.

  ProjectManager 메서드   ↔  Spring 대응
  ────────────────────────────────────────────
  create_project()        ↔  ProjectService.create()
  get_project_or_raise()  ↔  ProjectService.getOrThrow()  (404 예외 포함)
  update_project()        ↔  ProjectService.update()
  rename_project()        ↔  ProjectService.rename()  (ID 재생성 포함)
  delete_project()        ↔  ProjectService.delete()
  list_projects()         ↔  ProjectService.findAll(filters)
  add_task()              ↔  TaskService.addToProject()
  update_task()           ↔  TaskService.update()
  delete_task()           ↔  TaskService.delete()
"""

from __future__ import annotations

# uuid : 범용 고유 식별자 생성 표준 라이브러리.
# [Spring] java.util.UUID 와 동일.
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
    """프로젝트/작업 비즈니스 로직 담당 서비스.

    [Spring 비교]
      @Service @Transactional 어노테이션을 붙이는 서비스 클래스.
      인스턴스 상태는 없으므로 모든 메서드는 내부적으로 stateless 하게 동작.
    """

    # @staticmethod : 인스턴스(self) 없이 호출 가능한 정적 메서드.
    # [Spring] public static 메서드 — 유틸리티 성격의 내부 헬퍼.
    @staticmethod
    def _clean_string_list(values: Optional[list[str]]) -> list[str]:
        """null/빈 문자열을 제거하고 strip 한 리스트를 반환한다."""
        # [Spring] list.stream().map(String::strip).filter(s -> !s.isEmpty()).collect(toList()).
        return [value.strip() for value in (values or []) if value and value.strip()]

    @staticmethod
    def _next_task_id(used_ids: Optional[set[str]] = None) -> str:
        """충돌 없는 새 작업 ID 를 생성한다.

        형식: task_<UUID 8자리 hex>  예) task_a1b2c3d4
        """
        used = used_ids or set()
        # while True : 무한 루프. 중복이 없을 때까지 반복.
        # [Spring] do { ... } while (used.contains(candidate)); 와 동일.
        while True:
            # uuid.uuid4() : 랜덤 UUID 생성. [Spring] UUID.randomUUID().
            # .hex : UUID 를 하이픈 없는 32자리 16진수 문자열로 변환.
            # [:8] : 슬라이싱 — 첫 8자리만 사용. [Spring] uuid.toString().substring(0, 8).
            candidate = f"task_{uuid.uuid4().hex[:8]}"
            if candidate not in used:
                return candidate

    def _next_project_id(self, name: str, exclude_project_id: Optional[str] = None) -> str:
        """프로젝트명으로 고유 ID 를 생성한다.

        - 정확히 같은 이름이 이미 있으면 DevfolioError 발생
        - ID 정규화 충돌은 suffix(_2, _3, ...)로 해소

        [Spring 비교]
          DB 의 UNIQUE 제약 체크를 코드 레벨에서 미리 수행하는 것.
          JPA 에서 @UniqueConstraint 위반 시 DataIntegrityViolationException 을 던지는 것과 유사.
        """
        projects = list_projects()

        # 동일 이름이 이미 존재하면 즉시 오류.
        for project in projects:
            # exclude_project_id : 자기 자신은 제외 (rename 시 본인과 비교하지 않도록).
            if project.id != exclude_project_id and project.name == name:
                raise DevfolioError(
                    f"이미 같은 이름의 프로젝트가 있습니다: '{name}'",
                    hint="`devfolio project list`로 기존 프로젝트를 확인하세요.",
                )

        base_id = project_id_from_name(name)
        # set comprehension : 조건에 맞는 값만으로 set 을 만든다.
        # [Spring] projects.stream().map(Project::getId).filter(...).collect(toSet()).
        used_ids = {project.id for project in projects if project.id != exclude_project_id}

        if base_id not in used_ids:
            return base_id

        # ID 충돌 시 _2, _3, ... suffix 를 붙여 해소.
        for index in range(2, 100):
            candidate = f"{base_id}_{index}"
            if candidate not in used_ids:
                return candidate

        raise DevfolioError(
            f"프로젝트 ID를 생성할 수 없습니다: '{name}'",
            hint="프로젝트명을 더 구체적으로 지정하세요.",
        )

    def draft_from_project(self, project: Project) -> ProjectDraft:
        """저장된 Project 를 웹 편집용 ProjectDraft 로 변환한다.

        [Spring 비교]
          Entity → DTO 변환. BeanUtils.copyProperties(entity, dto) 와 동일한 역할.
        """
        # project.model_dump() : Project → dict.
        # ProjectDraft.model_validate(dict) : dict → ProjectDraft.
        # 두 단계로 변환함으로써 필드 이름이 같으면 자동 매핑된다.
        return ProjectDraft.model_validate(project.model_dump())

    def project_from_draft(
        self,
        draft: ProjectDraft,
        project_id: Optional[str] = None,
        *,
        # * : 이 뒤의 인수는 반드시 키워드 인수로만 넘길 수 있다.
        # [Spring] Builder 패턴에서 특정 값만 명시적으로 지정하는 것과 유사.
        transient: bool = False,
    ) -> Project:
        """Draft(웹 편집 중간 상태)를 Project 도메인 모델로 변환한다.

        transient=True 이면 저장하지 않는 미리보기용 Project 를 만든다.
        [Spring 비교]
          DTO → Entity 역변환. @Transient 필드와 유사한 개념 (저장 안 함).
        """
        project_name = (draft.name or "").strip() or ("Untitled Project" if transient else "")
        if not project_name:
            raise DevfolioError(
                "프로젝트명은 비워둘 수 없습니다.",
                hint="초안 검토 단계에서 프로젝트명을 먼저 입력하세요.",
            )

        # (A or B).strip() : A 가 falsy 이면 B 를 사용하고 strip(). Java 의 삼항 연산자 대체.
        resolved_id = (project_id or draft.id or "").strip()
        if not resolved_id:
            base_name = draft.name.strip() if draft.name.strip() else "draft_project"
            resolved_id = project_id_from_name(base_name)

        used_task_ids: set[str] = set()
        tasks: list[Task] = []
        for task_draft in draft.tasks:
            task_name = (task_draft.name or "").strip() or "Untitled Task"
            task_id = (task_draft.id or "").strip()
            # ID 가 없거나 중복이면 새로 생성.
            if not task_id or task_id in used_task_ids:
                task_id = self._next_task_id(used_task_ids)
            used_task_ids.add(task_id)

            tasks.append(
                Task(
                    id=task_id,
                    name=task_name,
                    # Period.model_validate(dict) : Period VO 를 dict 에서 재생성.
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
        """웹 편집 초안을 실제 Project 로 저장한다.

        project_id 가 있으면 기존 프로젝트를 갱신하고, 없으면 신규 등록한다.
        [Spring 비교]
          JpaRepository.save() — persist(신규) or merge(갱신).
        """
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

        updated_project = self.project_from_draft(draft, project_id=target.id)
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
        """프로젝트 요약(summary 필드)을 저장한다."""
        return self.update_project(name_or_id, summary=summary)

    # ------------------------------------------------------------------
    # 프로젝트 CRUD
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
        """새 프로젝트를 생성하고 YAML 파일로 저장한다.

        [Spring 비교]
          ProjectService.create(dto) — DTO 를 받아 Entity 로 변환 후 save.
        """
        project_id = self._next_project_id(name)

        project = Project(
            id=project_id,
            name=name,
            type=type,
            status=status,
            organization=organization,
            # Period(start=..., end=...) : 기간 VO 생성.
            # "" or None → None 으로 정규화 (Period.validate_yyyymm 이 처리).
            period=Period(start=period_start or None, end=period_end or None),
            role=role,
            team_size=team_size,
            # tech_stack or [] : tech_stack 이 None 이면 빈 리스트 사용.
            tech_stack=tech_stack or [],
            summary=summary,
            tags=tags or [],
            tasks=[],
        )
        save_project(project)
        return project

    def get_project(self, name_or_id: str) -> Optional[Project]:
        """이름 또는 ID 로 프로젝트를 검색한다. 없으면 None.

        [Spring 비교]
          ProjectRepository.findById() → Optional<Project>.
        """
        return find_project_by_name(name_or_id)

    def get_project_or_raise(self, name_or_id: str) -> Project:
        """이름 또는 ID 로 프로젝트를 검색한다. 없으면 DevfolioProjectNotFoundError.

        [Spring 비교]
          ProjectRepository.findById().orElseThrow(NotFoundException::new).
        """
        project = find_project_by_name(name_or_id)
        if not project:
            raise DevfolioProjectNotFoundError(name_or_id)
        return project

    def update_project(self, name_or_id: str, **kwargs) -> Project:
        """프로젝트 필드를 업데이트한다.

        **kwargs : 가변 키워드 인수. 어떤 필드든 키=값 형태로 넘길 수 있다.
        [Spring 비교]
          @PatchMapping — 일부 필드만 업데이트. Map<String, Object> 로 전달하는 패턴.
        """
        project = self.get_project_or_raise(name_or_id)
        # model_copy(update={...}) : Pydantic 불변 업데이트.
        #   기존 객체를 복사하면서 update dict 의 필드만 덮어씌운다.
        #   [Spring] BeanUtils.copyProperties(source, target) + 개별 필드 오버라이드.
        # {k: v for k, v in kwargs.items() if v is not None} : None 값은 무시.
        #   [Spring] map.entrySet().stream().filter(e -> e.getValue() != null).collect(...).
        updated = project.model_copy(update={k: v for k, v in kwargs.items() if v is not None})
        save_project(updated)
        return updated

    def rename_project(self, name_or_id: str, new_name: str, **kwargs) -> Project:
        """프로젝트명을 변경하고 필드를 업데이트한다.

        이름이 달라지면 ID 도 재생성하며, 기존 파일을 삭제한다.
        [Spring 비교]
          Entity rename → DB 에서 기존 row 삭제 + 새 row 삽입 (파일 기반이므로 동일 패턴).
        """
        project = self.get_project_or_raise(name_or_id)

        # {k: v ... if v is not None} : None 이 아닌 필드만 모아 dict 로.
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if new_name != project.name:
            updates["name"] = new_name
            # ID 변경 — 새 이름 기반으로 재생성 (기존 ID 제외하고 충돌 체크).
            updates["id"] = self._next_project_id(new_name, exclude_project_id=project.id)
        else:
            updates["name"] = project.name
            updates["id"] = project.id

        updated = project.model_copy(update=updates)
        save_project(updated)
        # ID 가 바뀌었으면 이전 파일 삭제.
        if updated.id != project.id:
            delete_project_file(project.id)
        return updated

    def delete_project(self, name_or_id: str) -> bool:
        """프로젝트를 삭제한다. 없으면 DevfolioProjectNotFoundError.

        [Spring 비교]
          ProjectService.deleteOrThrow(id).
        """
        project = self.get_project_or_raise(name_or_id)
        return delete_project_file(project.id)

    def list_projects(
        self,
        stack_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
    ) -> list[Project]:
        """조건에 맞는 프로젝트 목록을 반환한다.

        [Spring 비교]
          ProjectRepository.findAll(Specification) — 필터 조합으로 조회.
        """
        projects = list_projects()
        # stack_filter 가 있으면 tech_stack 에 해당 값이 포함된 것만 남긴다.
        # [Spring] stream().filter(p -> p.getTechStack().stream().anyMatch(...)).
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
        """프로젝트에 새 작업 내역을 추가한다.

        [Spring 비교]
          TaskService.addToProject(projectId, taskDto) — @OneToMany 추가 후 save.
        """
        project = self.get_project_or_raise(project_name)
        task = Task(
            # {t.id for t in project.tasks} : 기존 Task ID 를 set 으로 수집.
            # [Spring] project.getTasks().stream().map(Task::getId).collect(toSet()).
            id=self._next_task_id({t.id for t in project.tasks}),
            name=name,
            period=Period(start=period_start or None, end=period_end or None),
            problem=problem,
            solution=solution,
            result=result,
            tech_used=tech_used or [],
            keywords=keywords or [],
        )
        # list.append() : 리스트 끝에 추가. [Spring] List.add(task).
        project.tasks.append(task)
        save_project(project)
        return task

    def _find_task(self, project: Project, task_name: str) -> Task:
        """프로젝트 내에서 이름 또는 ID 로 Task 를 찾는다.

        [Spring 비교]
          project.getTasks().stream().filter(t -> t.getName().equals(name) || t.getId().equals(id))
            .findFirst().orElseThrow(TaskNotFoundException::new).
        """
        # next(generator, default) : generator 에서 첫 번째 값을 가져오고, 없으면 default.
        # [Spring] stream().findFirst().orElse(null).
        task = next(
            (t for t in project.tasks if t.name == task_name or t.id == task_name),
            None,
        )
        if not task:
            raise DevfolioTaskNotFoundError(task_name, project.name)
        return task

    def get_task_or_raise(self, project_name: str, task_name: str) -> tuple[Project, Task]:
        """프로젝트와 Task 를 함께 반환한다. 없으면 예외 발생.

        tuple[A, B] : 두 값을 하나로 묶어 반환. [Spring] Pair<Project, Task> 와 유사.
        """
        project = self.get_project_or_raise(project_name)
        task = self._find_task(project, task_name)
        return project, task

    def update_task(self, project_name: str, task_name: str, **kwargs) -> Task:
        """작업 내역을 수정한다. 내용 변경 시 AI 캐시를 자동 무효화한다.

        [Spring 비교]
          @Modifying @Transactional — 업데이트 + 캐시 무효화 @CacheEvict 와 동일한 개념.
        """
        project, task = self.get_task_or_raise(project_name, task_name)

        # content_fields & set(kwargs.keys()) : 두 집합의 교집합.
        #   어느 하나라도 내용 관련 필드가 변경됐으면 AI 캐시를 초기화.
        #   [Spring] CollectionUtils.containsAny(contentFields, kwargs.keySet()).
        content_fields = {"problem", "solution", "result", "tech_used", "name"}
        invalidate_cache = bool(content_fields & set(kwargs.keys()))

        updates = {k: v for k, v in kwargs.items() if v is not None}
        if invalidate_cache:
            # AI 캐시 무효화 — 내용이 바뀌었으므로 이전 AI 생성 문구를 비운다.
            updates["ai_generated_text"] = ""

        # task.model_copy(update=updates) : task 객체를 복사하면서 일부 필드만 변경.
        # Pydantic 모델은 기본적으로 불변(immutable) — 직접 필드를 수정하는 것보다 이 방법을 권장.
        updated_task = task.model_copy(update=updates)
        # list comprehension 으로 tasks 리스트에서 해당 task 만 교체.
        # [Spring] tasks.replaceAll(t -> t.getId().equals(task.getId()) ? updatedTask : t).
        project.tasks = [
            updated_task if t.id == task.id else t for t in project.tasks
        ]
        save_project(project)
        return updated_task

    def delete_task(self, project_name: str, task_name: str) -> bool:
        """작업 내역을 삭제한다. 없으면 False 반환.

        [Spring 비교]
          TaskRepository.delete(task) — 없어도 예외 없이 False 반환.
        """
        project = self.get_project_or_raise(project_name)
        task = next(
            (t for t in project.tasks if t.name == task_name or t.id == task_name),
            None,
        )
        if not task:
            return False
        # 필터링으로 해당 task 제외. [Spring] tasks.removeIf(t -> t.getId().equals(task.getId())).
        project.tasks = [t for t in project.tasks if t.id != task.id]
        save_project(project)
        return True

    def save_task_ai_text(
        self, project_name: str, task_name: str, ai_text: str
    ) -> bool:
        """AI 생성 문구를 작업 내역에 캐싱한다. 성공이면 True.

        [Spring 비교]
          @CachePut — 생성된 AI 텍스트를 Entity 에 저장하는 것과 동일.
        """
        try:
            project, task = self.get_task_or_raise(project_name, task_name)
            updated_task = task.model_copy(update={"ai_generated_text": ai_text})
            project.tasks = [
                updated_task if t.id == task.id else t for t in project.tasks
            ]
            save_project(project)
            return True
        except Exception:
            # 어떤 예외도 호출자에게 전파하지 않고 False 반환.
            return False

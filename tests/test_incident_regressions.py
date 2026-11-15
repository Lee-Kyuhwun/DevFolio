"""실서비스에서 발견된 장애의 회귀 테스트.

각 테스트 이름의 incNN은 docs/agent-incidents.md 의 INC-NN 항목과 1:1로 대응한다.
조치 코드를 되돌리면 해당 테스트가 실패하는지 확인한 결과도 기록부에 남긴다.
"""

import importlib
import json
import pkgutil
import sys
import zipfile
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import devfolio
from devfolio.core import storage
from devfolio.core.ai_service import AIService, _strip_foreign_chars
from devfolio.exceptions import DevfolioAIError
from devfolio.models.config import AIProviderConfig
from devfolio.models.config import Config, UserConfig
from devfolio.models.project import Period, Project
from tests.test_ai_service import make_config

# 모듈 import 시점의 실제 경로 (테스트 중에는 conftest가 임시 경로로 바꾼다)
_USER_AI_LOG_FILE = storage.AI_LOG_FILE


@pytest.fixture
def audit_store(tmp_path, monkeypatch):
    """OS별 디렉터리 이름 중복까지 재현하며 실제 사용자 파일을 격리한다."""
    config_dir = tmp_path / "preferences" / "devfolio"
    data_dir = tmp_path / "application-support" / "devfolio"
    legacy_dir = tmp_path / "legacy" / ".devfolio"
    for name, value in {
        "DEVFOLIO_CONFIG_DIR": config_dir,
        "DEVFOLIO_DATA_DIR": data_dir,
        "CONFIG_FILE": config_dir / "config.yaml",
        "PROJECTS_DIR": data_dir / "projects",
        "EXPORTS_DIR": data_dir / "exports",
        "TEMPLATES_DIR": data_dir / "templates",
        "_LEGACY_HOME": legacy_dir,
        "_LEGACY_CONFIG": legacy_dir / "config.yaml",
    }.items():
        monkeypatch.setattr(storage, name, value)
    storage.ensure_dirs()
    return tmp_path


def test_inc13_exact_project_name_wins_over_normalized_id(audit_store):
    from devfolio.core.project_manager import ProjectManager

    manager = ProjectManager()
    first = manager.create_project("a b", summary="first")
    second = manager.create_project("A B", summary="second")

    assert manager.get_project("A B").id == second.id
    manager.delete_project("A B")
    assert storage.load_project(second.id) is None
    assert storage.load_project(first.id).summary == "first"


def test_inc13_import_does_not_overwrite_partial_name_match(audit_store):
    from typer.testing import CliRunner

    from devfolio.core.project_manager import ProjectManager
    from devfolio.main import app

    storage.save_config(Config())
    manager = ProjectManager()
    original = manager.create_project("Backend API", summary="original")
    source = audit_store / "import.json"
    source.write_text(json.dumps({"name": "Backend", "summary": "new"}))
    result = CliRunner().invoke(app, ["data", "import", str(source), "--yes"])

    assert result.exit_code == 0, result.output
    assert storage.load_project(original.id).summary == "original"
    assert len(storage.list_projects()) == 2


def test_inc13_import_rejects_id_owned_by_a_different_project(audit_store):
    from typer.testing import CliRunner

    from devfolio.core.project_manager import ProjectManager
    from devfolio.main import app

    storage.save_config(Config())
    original = ProjectManager().create_project("Original", summary="keep")
    source = audit_store / "collision.json"
    source.write_text(json.dumps({"id": original.id, "name": "Different"}))

    result = CliRunner().invoke(app, ["data", "import", str(source), "--yes"])

    assert result.exit_code == 1
    assert "import 완료" not in result.output
    assert storage.load_project(original.id).summary == "keep"


def test_inc13_empty_lookup_never_selects_a_project(audit_store):
    storage.save_project(Project(id="demo", name="Demo"))
    assert storage.find_project_by_name("") is None


def test_inc14_backup_round_trip_separates_config_and_data(audit_store):
    storage.save_config(Config(user=UserConfig(name="backup-user")))
    storage.save_project(Project(id="demo", name="Demo"))
    archive = audit_store / "backup.zip"
    storage.backup(archive)
    storage.CONFIG_FILE.unlink()
    (storage.PROJECTS_DIR / "demo.yaml").unlink()

    storage.restore(archive)

    assert storage.load_config().user.name == "backup-user"
    assert storage.load_project("demo").name == "Demo"
    assert storage.CONFIG_FILE.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("root", ["devfolio", ".devfolio"])
def test_inc14_restore_old_backups_into_current_paths(audit_store, root):
    archive = audit_store / "old.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(f"{root}/config.yaml", "user:\n  name: restored\n")
        zf.writestr(f"{root}/projects/demo.yaml", "id: demo\nname: Demo\n")

    storage.restore(archive)

    assert storage.load_config().user.name == "restored"
    assert storage.load_project("demo").name == "Demo"
    assert storage.CONFIG_FILE.stat().st_mode & 0o777 == 0o600


def test_inc14_invalid_backup_does_not_partially_overwrite(audit_store):
    from devfolio.exceptions import DevfolioError

    storage.save_config(Config(user=UserConfig(name="original")))
    original = storage.CONFIG_FILE.read_bytes()
    archive = audit_store / "invalid.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("devfolio/config.yaml", "user:\n  name: changed\n")
        zf.writestr("devfolio/projects/broken.yaml", "name: [\n")

    with pytest.raises(DevfolioError) as exc:
        storage.restore(archive)
    assert exc.value.hint
    assert storage.CONFIG_FILE.read_bytes() == original
    assert list(storage.PROJECTS_DIR.iterdir()) == []


def test_inc14_backup_inside_data_dir_excludes_itself(audit_store):
    archive = storage.EXPORTS_DIR / "backup.zip"
    storage.save_project(Project(id="demo", name="Demo"))
    storage.backup(archive)

    with zipfile.ZipFile(archive) as zf:
        assert not any(name.endswith("backup.zip") for name in zf.namelist())


def test_inc14_restore_write_failure_rolls_back_written_files(audit_store, monkeypatch):
    from devfolio.exceptions import DevfolioError

    storage.save_config(Config(user=UserConfig(name="original")))
    original = storage.CONFIG_FILE.read_bytes()
    archive = audit_store / "write-failure.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("config/config.yaml", "user:\n  name: changed\n")
        zf.writestr("data/projects/demo.yaml", "id: demo\nname: Demo\n")
    atomic_write = storage._atomic_write

    def fail_project_write(path, content, mode=0o600):
        if path.parent == storage.PROJECTS_DIR:
            raise OSError("disk full")
        atomic_write(path, content, mode)

    monkeypatch.setattr(storage, "_atomic_write", fail_project_write)
    with pytest.raises(DevfolioError):
        storage.restore(archive)
    assert storage.CONFIG_FILE.read_bytes() == original
    assert storage.load_project("demo") is None


@pytest.mark.parametrize(
    "member", ["../config.yaml", "/devfolio/config.yaml", "data/../config.yaml"]
)
def test_inc14_restore_rejects_unsafe_paths(audit_store, member):
    from devfolio.exceptions import DevfolioError

    archive = audit_store / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(member, "user:\n  name: unsafe\n")
    with pytest.raises(DevfolioError):
        storage.restore(archive)
    assert not storage.CONFIG_FILE.exists()


@pytest.mark.parametrize("kind", ["project", "config"])
def test_inc15_failed_yaml_write_preserves_original(audit_store, monkeypatch, kind):
    from ruamel.yaml import YAML

    from devfolio.exceptions import DevfolioError

    model = Project(id="demo", name="Original") if kind == "project" else Config()
    save = storage.save_project if kind == "project" else storage.save_config
    path = (
        storage.PROJECTS_DIR / "demo.yaml" if kind == "project" else storage.CONFIG_FILE
    )
    save(model)
    original = path.read_bytes()

    def fail_dump(self, data, stream, **kwargs):
        stream.write("partial:")
        raise OSError("disk full")

    monkeypatch.setattr(YAML, "dump", fail_dump)
    with pytest.raises(DevfolioError) as exc:
        save(model)
    assert exc.value.hint
    assert path.read_bytes() == original
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]


def test_inc15_failed_replace_preserves_original_and_cleans_temp(
    audit_store, monkeypatch
):
    from pathlib import Path

    from devfolio.exceptions import DevfolioError

    storage.save_config(Config(user=UserConfig(name="original")))
    original = storage.CONFIG_FILE.read_bytes()

    def fail_replace(self, target):
        raise PermissionError("replacement denied")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(DevfolioError):
        storage.save_config(Config(user=UserConfig(name="changed")))
    assert storage.CONFIG_FILE.read_bytes() == original
    assert list(storage.CONFIG_FILE.parent.iterdir()) == [storage.CONFIG_FILE]


@pytest.mark.parametrize(
    "payload",
    [
        {"start": "2024-00"},
        {"end": "2024-13"},
        {"start": "0000-01"},
        {"start": "2024-06", "end": "2024-01"},
    ],
)
def test_inc16_invalid_period_is_rejected(payload):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Period.model_validate(payload)


def test_inc16_invalid_update_keeps_stored_project_readable(audit_store):
    from devfolio.core.project_manager import ProjectManager
    from devfolio.exceptions import DevfolioError

    manager = ProjectManager()
    project = manager.create_project("Demo")
    path = storage.PROJECTS_DIR / f"{project.id}.yaml"
    original = path.read_bytes()

    with pytest.raises(DevfolioError) as exc:
        manager.update_project(project.id, team_size=0)
    assert exc.value.hint
    assert path.read_bytes() == original
    assert storage.load_project(project.id).team_size == 1


def test_inc16_project_id_cannot_escape_projects_dir(audit_store):
    from devfolio.exceptions import DevfolioError

    with pytest.raises(DevfolioError):
        storage.save_project(Project(id="../outside", name="Unsafe"))
    assert not (storage.DEVFOLIO_DATA_DIR / "outside.yaml").exists()


def test_inc16_whitespace_name_cannot_overwrite_existing_project(audit_store):
    from devfolio.core.project_manager import ProjectManager
    from devfolio.exceptions import DevfolioError

    manager = ProjectManager()
    original = manager.create_project("Demo", summary="keep")
    with pytest.raises(DevfolioError):
        manager.create_project(" Demo ", summary="replace")
    assert storage.load_project(original.id).summary == "keep"


def test_inc16_blank_project_name_is_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Project(id="empty", name="  ")


def test_inc16_cli_validation_error_has_hint_without_traceback(
    audit_store, monkeypatch, capsys
):
    from devfolio import main

    def invalid_command():
        Period(start="2024-13")

    monkeypatch.setattr(main, "app", invalid_command)
    with pytest.raises(SystemExit) as exc:
        main.cli()
    assert exc.value.code == 1
    output = capsys.readouterr().err
    assert "입력값" in output
    assert "다시 시도" in output
    assert "Traceback" not in output


@pytest.mark.parametrize(
    "content",
    [
        "<script>window.parent.document.body.remove()</script>",
        '<img src="x" onerror="alert(1)">',
        "[click](javascript:alert%281%29)",
        '<a href="java&#x73;cript:alert(1)">click</a>',
        '<svg onload="alert(1)"></svg>',
    ],
)
def test_inc17_html_preview_never_emits_executable_user_markup(
    audit_store, monkeypatch, content
):
    from html.parser import HTMLParser

    from devfolio.core import export_engine

    monkeypatch.setattr(export_engine, "EXPORTS_DIR", storage.EXPORTS_DIR)
    rendered = export_engine.ExportEngine()._md_to_html_body(content)
    dangerous = []

    class Inspector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag in {"script", "svg", "iframe", "object", "embed"}:
                dangerous.append(tag)
            for key, value in attrs:
                if key.startswith("on") or (
                    key in {"href", "src"}
                    and (value or "").lower().startswith("javascript:")
                ):
                    dangerous.append(key)

    Inspector().feed(rendered)
    assert dangerous == []


def test_inc17_html_keeps_markdown_links_tables_and_mermaid(audit_store, monkeypatch):
    from devfolio.core import export_engine

    monkeypatch.setattr(export_engine, "EXPORTS_DIR", storage.EXPORTS_DIR)
    rendered = export_engine.ExportEngine()._md_to_html_body(
        "[GitHub](https://github.com/example)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```mermaid\ngraph TD\nA-->B\n```"
    )
    assert 'href="https://github.com/example"' in rendered
    assert "<table>" in rendered
    assert 'class="language-mermaid"' in rendered


def test_inc18_export_rejects_parent_traversal(audit_store):
    from devfolio.core.export_engine import _validate_output_path
    from devfolio.exceptions import DevfolioExportError

    with pytest.raises(DevfolioExportError):
        _validate_output_path(audit_store / "subdir" / ".." / "resume.md")


def test_inc18_export_rejects_sibling_with_same_prefix(audit_store, monkeypatch):
    from pathlib import Path

    from devfolio.core.export_engine import _validate_output_path
    from devfolio.exceptions import DevfolioExportError

    allowed = audit_store / "allowed"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: allowed))
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: allowed))
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(allowed))
    with pytest.raises(DevfolioExportError):
        _validate_output_path(audit_store / "allowed-sibling" / "resume.md")


def _response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _error(class_name: str, message: str) -> Exception:
    return type(class_name, (Exception,), {})(message)


# pyproject 선택 의존성(ai, pdf, docx, gui)의 최상위 모듈.
# `pip install -e ".[dev]"`만 설치한 환경에서는 없을 수 있으므로 import 실패가 아니라 건너뜀으로 본다.
_OPTIONAL_DEPENDENCIES = frozenset(
    {"litellm", "weasyprint", "markdown", "docx", "fastapi", "uvicorn"}
)


def _import_all_devfolio_modules() -> tuple[dict[str, str], dict[str, str]]:
    """devfolio 하위 모듈을 모두 import한다. (실패, 선택 의존성 때문에 건너뜀)을 반환한다."""
    failures: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for module in pkgutil.walk_packages(devfolio.__path__, "devfolio."):
        try:
            importlib.import_module(module.name)
        except ModuleNotFoundError as e:
            if (e.name or "").split(".")[0] in _OPTIONAL_DEPENDENCIES:
                skipped[module.name] = e.name
            else:
                failures[module.name] = f"ModuleNotFoundError: {e}"
        except Exception as e:  # noqa: BLE001 — 문법 오류 등 모든 import 실패를 모아서 보여준다
            failures[module.name] = f"{type(e).__name__}: {e}"
    return failures, skipped


@contextmanager
def _offline_litellm(fake_litellm: MagicMock):
    """실제 API·사용자 데이터 폴더·대기 없이 AIService 호출 경로를 실행한다."""
    with (
        patch("devfolio.core.ai_service.get_api_key", return_value="sk-test"),
        patch("devfolio.core.ai_service._write_ai_log"),
        patch("devfolio.core.ai_service.time.sleep") as sleep,
        patch.dict("sys.modules", {"litellm": fake_litellm}),
        patch.dict("os.environ", {}, clear=False),
    ):
        yield sleep


def test_inc01_quota_zero_fails_without_retry():
    service = AIService(make_config("gemini"))
    provider = service._get_provider("gemini")
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = _error(
        "RateLimitError",
        "Quota exceeded for metric: generativelanguage.googleapis.com/"
        "generate_content_free_tier_requests, limit: 0",
    )

    with (
        _offline_litellm(fake_litellm) as sleep,
        patch.object(
            service, "_runtime_model_candidates", return_value=["gemini-2.5-flash"]
        ),
    ):
        with pytest.raises(DevfolioAIError) as exc:
            service._call_single_provider(
                fake_litellm,
                provider,
                [{"role": "user", "content": "x"}],
                None,
                None,
                False,
            )

    assert fake_litellm.completion.call_count == 1
    assert "결제" in exc.value.hint
    sleep.assert_not_called()


def test_inc02_not_found_model_moves_to_next_candidate_without_wait():
    service = AIService(make_config("gemini"))
    provider = service._get_provider("gemini")
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = [
        _error("NotFoundError", "model not found"),
        _response("정상 응답"),
    ]

    with (
        _offline_litellm(fake_litellm) as sleep,
        patch.object(
            service,
            "_runtime_model_candidates",
            return_value=["retired-model", "current-model"],
        ),
    ):
        result = service._call_single_provider(
            fake_litellm,
            provider,
            [{"role": "user", "content": "x"}],
            None,
            None,
            False,
        )

    assert result == "정상 응답"
    assert "current-model" in fake_litellm.completion.call_args_list[1].kwargs["model"]
    sleep.assert_not_called()


def test_inc03_extracts_json_wrapped_in_fence_or_prose():
    fenced = '네, 아래와 같습니다.\n```json\n{"a": 1}\n```\n참고하세요.'
    prose = '요청하신 결과입니다: {"a": 1} 이상입니다.'

    assert AIService._extract_json(fenced) == {"a": 1}
    assert AIService._extract_json(prose) == {"a": 1}


def test_inc04_strips_japanese_and_chinese_but_keeps_korean():
    out = _strip_foreign_chars("Redis 캐시를 導入して 응답 시간을 단축했습니다")

    assert not any(
        0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in out
    )
    assert "Redis" in out
    assert "응답 시간을 단축했습니다" in out


def test_inc05_empty_response_falls_back_to_next_provider():
    config = make_config("anthropic")
    config.ai_providers.append(
        AIProviderConfig(name="openai", model="gpt-4o", key_stored=True)
    )
    service = AIService(config)
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = [
        _response("   "),
        _response("다음 provider 응답"),
    ]

    with (
        _offline_litellm(fake_litellm),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
    ):
        result = service._call_messages([{"role": "user", "content": "x"}])

    assert result == "다음 provider 응답"
    assert "gpt-4o" in fake_litellm.completion.call_args_list[1].kwargs["model"]


def test_ai_logs_during_tests_stay_out_of_user_data_dir():
    assert storage.AI_LOG_FILE != _USER_AI_LOG_FILE

    test_inc02_not_found_model_moves_to_next_candidate_without_wait()

    assert storage.AI_LOG_FILE.exists()


def test_inc06_missing_optional_dependency_is_skipped_not_failed():
    web_modules = [name for name in sys.modules if name.startswith("devfolio.web")]
    with patch.dict("sys.modules", {"fastapi": None}):
        for name in web_modules:
            sys.modules.pop(name)
        failures, skipped = _import_all_devfolio_modules()

    assert failures == {}
    assert "devfolio.web.routes.api" in skipped


def test_inc06_every_devfolio_module_imports():
    names = [m.name for m in pkgutil.walk_packages(devfolio.__path__, "devfolio.")]
    assert "devfolio.web.main" in names

    failures, _ = _import_all_devfolio_modules()

    assert failures == {}


# 2026-10-03 실제 실행에서 받은 pollinations 응답 (HTTP 200, 본문이 거절 문구)
_CREDIT_REFUSAL = (
    "The account behind this API key doesn't have enough credits. "
    "Please [top up](https://enter.pollinations.ai) to continue."
)


def test_inc09_credit_refusal_text_falls_back_to_next_provider():
    config = make_config("anthropic")
    config.ai_providers.append(
        AIProviderConfig(name="openai", model="gpt-4o", key_stored=True)
    )
    service = AIService(config)
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = [
        _response(_CREDIT_REFUSAL),
        _response("다음 provider 응답"),
    ]

    with (
        _offline_litellm(fake_litellm),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
    ):
        result = service._call_messages([{"role": "user", "content": "x"}])

    assert result == "다음 provider 응답"


def test_inc09_credit_refusal_text_is_never_returned_as_a_draft():
    service = AIService(make_config("anthropic"))
    fake_litellm = MagicMock()
    fake_litellm.completion.return_value = _response(_CREDIT_REFUSAL)

    with (
        _offline_litellm(fake_litellm),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
    ):
        with pytest.raises(DevfolioAIError):
            service._call_messages([{"role": "user", "content": "x"}])


def test_inc10_tests_never_touch_the_real_keychain():
    import keyring

    from tests.conftest import InMemoryKeyring

    assert isinstance(keyring.get_keyring(), InMemoryKeyring)


def test_inc11_judge_call_leaves_room_for_thinking_tokens():
    """추론(thinking) 모델은 생각 토큰도 출력 한도에서 쓴다. 1,200이면 심사 JSON이 잘렸다."""
    import json

    from devfolio.core.ai_service import GenerationProfile, PortfolioEvidence

    service = AIService(make_config("gemini"))
    captured = {}
    scores = dict.fromkeys(
        [
            "factuality",
            "specificity",
            "result_orientation",
            "hiring_relevance",
            "redundancy",
            "output_contract",
            "naturalness",
        ],
        4,
    )

    def fake_call(messages, **kwargs):
        captured.update(kwargs)
        return json.dumps({"pass": True, "scores": scores})

    with patch.object(service, "_call_messages", side_effect=fake_call):
        service._review_generated_text(
            service._prompt_pack("ko"),
            PortfolioEvidence(name="x"),
            "요약",
            GenerationProfile(mode="project_summary"),
            None,
        )

    assert captured["max_tokens"] >= 4096


def test_inc12_daily_free_tier_limit_is_not_reported_as_zero_quota():
    """INC-01 판정이 넓어서 '하루 20회 한도 소진'을 '할당량 0'으로 오판했다."""
    from devfolio.exceptions import DevfolioAIRateLimitError

    service = AIService(make_config("gemini"))
    provider = service._get_provider("gemini")
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = _error(
        "RateLimitError",
        "RESOURCE_EXHAUSTED Quota exceeded for metric: generativelanguage.googleapis.com/"
        "generate_content_free_tier_requests, limit: 20, model: gemini-3-flash "
        "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
    )

    with (
        _offline_litellm(fake_litellm),
        patch.object(
            service,
            "_runtime_model_candidates",
            return_value=["gemini-3-flash-preview"],
        ),
    ):
        with pytest.raises(DevfolioAIRateLimitError) as exc:
            service._call_single_provider(
                fake_litellm,
                provider,
                [{"role": "user", "content": "x"}],
                None,
                None,
                False,
            )

    assert "0입니다" not in str(exc.value)


# ---------------------------------------------------------------------------
# INC-21: Groq 후보 전멸 + 출력 토큰 한도 절단으로 AI 딥 분석이 항상 실패
# ---------------------------------------------------------------------------


def _response_with_finish_reason(
    text: str, finish_reason: str | None
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text),
                finish_reason=finish_reason,
            )
        ]
    )


def test_inc21_truncated_response_moves_to_next_candidate_without_retry():
    """finish_reason=length로 잘린 응답이 'JSON 파싱 실패'로 둔갑해 원인을 가렸다."""
    service = AIService(make_config("gemini"))
    provider = service._get_provider("gemini")
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = [
        _response_with_finish_reason(
            '{"project_type": "CLI 도구", "tasks": [{"name": "GitH', "length"
        ),
        _response('{"project_type": "CLI 도구"}'),
    ]

    with (
        _offline_litellm(fake_litellm) as sleep,
        patch.object(
            service,
            "_runtime_model_candidates",
            return_value=["truncating-model", "current-model"],
        ),
    ):
        result = service._call_single_provider(
            fake_litellm,
            provider,
            [{"role": "user", "content": "x"}],
            None,
            None,
            False,
        )

    assert result == '{"project_type": "CLI 도구"}'
    assert fake_litellm.completion.call_count == 2
    assert "current-model" in fake_litellm.completion.call_args_list[1].kwargs["model"]
    sleep.assert_not_called()


def test_inc21_decommissioned_model_is_not_retried():
    """400 model_decommissioned는 재시도해도 같은 결과인데 2회씩 낭비했다."""
    service = AIService(make_config("groq"))
    provider = service._get_provider("groq")
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = [
        _error(
            "BadRequestError",
            'GroqException - {"error":{"message":"The model `gemma2-9b-it` has been '
            'decommissioned and is no longer supported.","code":"model_decommissioned"}}',
        ),
        _response("정상 응답"),
    ]

    with (
        _offline_litellm(fake_litellm) as sleep,
        patch.object(
            service,
            "_runtime_model_candidates",
            return_value=["retired-model", "current-model"],
        ),
    ):
        result = service._call_single_provider(
            fake_litellm,
            provider,
            [{"role": "user", "content": "x"}],
            None,
            None,
            False,
        )

    assert result == "정상 응답"
    assert fake_litellm.completion.call_count == 2
    assert "current-model" in fake_litellm.completion.call_args_list[1].kwargs["model"]
    sleep.assert_not_called()


def test_inc21_code_analysis_requests_explicit_output_budget():
    """분석 경로만 max_tokens를 안 넘겨 provider 기본값(1500토큰)에 걸렸다."""
    service = AIService(make_config("groq"))
    captured: dict = {}

    def fake_call(
        system_prompt,
        user_prompt,
        provider_name=None,
        json_mode=False,
        max_tokens=None,
        **kwargs,
    ):
        captured["max_tokens"] = max_tokens
        return json.dumps({"project_type": "CLI 도구"})

    with (
        patch.object(service, "_call", side_effect=fake_call),
        patch.object(service, "_extract_problem_solving_cases", return_value=[]),
    ):
        service.analyze_project_from_code("repo", {}, {})

    assert captured["max_tokens"] == 2500


def test_inc21_request_timeout_is_always_sent():
    """응답이 없는 호출에 타임아웃이 없어 분석이 영구 대기했다."""
    from devfolio.core.ai_service import _REQUEST_TIMEOUT

    service = AIService(make_config("gemini"))
    provider = service._get_provider("gemini")
    fake_litellm = MagicMock()
    fake_litellm.completion.return_value = _response("ok")

    with (
        _offline_litellm(fake_litellm),
        patch.object(service, "_runtime_model_candidates", return_value=["m"]),
    ):
        service._call_single_provider(
            fake_litellm,
            provider,
            [{"role": "user", "content": "x"}],
            None,
            None,
            False,
        )

    assert fake_litellm.completion.call_args.kwargs["timeout"] == _REQUEST_TIMEOUT

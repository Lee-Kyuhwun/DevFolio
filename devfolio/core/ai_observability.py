"""AI 분석 관측(Observability) — 실행 상태·호출 이력·표준 오류 코드.

서버 로그에만 남던 정보(요청/실제 모델, 전환, 실패 원인)를 클라이언트가 읽을 수 있는
구조로 바꾼다. 이 모듈은 **상태의 단일 출처**다. API 응답과 UI 는 여기서 만든 스냅샷만
사용하므로, "서버는 실패인데 화면은 성공" 같은 불일치가 생기지 않는다.

저장: 데이터 디렉터리의 `ai_analysis_runs.json` (최근 20건).
  - 브라우저 새로고침·서버 재시작 후에도 상태를 복원할 수 있다.
  - 진행 중이던 실행은 재시작 시 CANCELLED 로 복구한다(끝나지 않은 작업을 완료로 보이지 않음).
  - 기술 상세(technical_message)는 파일에 저장하지 않고 프로세스 메모리에만 둔다.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from devfolio.core.ai_reliability import ErrorKind
from devfolio.log import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 상태 값
# ---------------------------------------------------------------------------

RUN_PENDING = "pending"
RUN_RUNNING = "running"
RUN_RETRYING = "retrying"
RUN_FALLBACK = "fallback"
RUN_VALIDATING = "validating"
RUN_COMPLETED = "completed"
RUN_PARTIAL = "partial"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

TERMINAL_STATUSES = frozenset({RUN_COMPLETED, RUN_PARTIAL, RUN_FAILED, RUN_CANCELLED})

STATUS_LABELS = {
    RUN_PENDING: "대기 중",
    RUN_RUNNING: "분석 중",
    RUN_RETRYING: "재시도 중",
    RUN_FALLBACK: "다른 모델로 전환 중",
    RUN_VALIDATING: "결과 검증 중",
    RUN_COMPLETED: "완료",
    RUN_PARTIAL: "일부 완료",
    RUN_FAILED: "실패",
    RUN_CANCELLED: "취소됨",
}

# 실제 파이프라인 순서 (ai_service.analyze_project_with_report 와 일치).
STAGE_DEFS: tuple[tuple[str, str], ...] = (
    ("scan", "Git 스캔"),
    ("analysis", "AI 초안 생성"),
    ("cases", "문제 해결 사례"),
    ("quality", "품질 검증"),
)
STAGE_IDS = tuple(stage_id for stage_id, _ in STAGE_DEFS)
STAGE_LABELS = dict(STAGE_DEFS)


# ---------------------------------------------------------------------------
# 표준 오류 코드
# ---------------------------------------------------------------------------


class ErrorCode:
    """클라이언트가 분기할 수 있는 오류 코드. (문자열 상수 모음)"""

    MODEL_DECOMMISSIONED = "MODEL_DECOMMISSIONED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    CONTEXT_LIMIT_EXCEEDED = "CONTEXT_LIMIT_EXCEEDED"
    OUTPUT_TRUNCATED = "OUTPUT_TRUNCATED"
    INVALID_JSON = "INVALID_JSON"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    QUALITY_GATE_FAILED = "QUALITY_GATE_FAILED"
    TOKEN_BUDGET_EXCEEDED = "TOKEN_BUDGET_EXCEEDED"
    ANALYSIS_CANCELLED = "ANALYSIS_CANCELLED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


ERROR_USER_MESSAGES: dict[str, str] = {
    ErrorCode.MODEL_DECOMMISSIONED: (
        "선택한 AI 모델은 더 이상 지원되지 않습니다. 사용 가능한 대체 모델로 전환을 시도합니다."
    ),
    ErrorCode.MODEL_NOT_FOUND: (
        "선택한 AI 모델을 찾을 수 없습니다. 모델 이름을 확인하거나 대체 모델로 전환해 주세요."
    ),
    ErrorCode.RATE_LIMITED: (
        "현재 AI 서비스의 요청 한도를 초과했습니다. 잠시 후 다시 시도하거나 "
        "다른 사용 가능한 모델을 선택해 주세요."
    ),
    ErrorCode.PROVIDER_UNAVAILABLE: (
        "AI 서비스가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해 주세요."
    ),
    ErrorCode.AUTHENTICATION_FAILED: (
        "AI 서비스 인증에 실패했습니다. 설정에서 API 키를 확인해 주세요."
    ),
    ErrorCode.PERMISSION_DENIED: (
        "이 모델을 사용할 권한이 없습니다. 다른 모델을 선택하거나 계정 권한을 확인해 주세요."
    ),
    ErrorCode.REQUEST_TIMEOUT: (
        "AI 응답이 제한 시간 안에 도착하지 않았습니다. 다시 시도해 주세요."
    ),
    ErrorCode.CONTEXT_LIMIT_EXCEEDED: (
        "분석할 내용이 모델이 처리할 수 있는 길이를 넘었습니다. "
        "저장소 범위를 줄이거나 더 큰 컨텍스트를 지원하는 모델을 선택해 주세요."
    ),
    ErrorCode.OUTPUT_TRUNCATED: (
        "AI 응답이 출력 길이 제한에 도달하여 분석 결과를 완성하지 못했습니다."
    ),
    ErrorCode.INVALID_JSON: (
        "AI가 응답했지만 분석 결과를 구조화된 형식으로 반환하지 못했습니다."
    ),
    ErrorCode.SCHEMA_VALIDATION_FAILED: (
        "AI가 응답했지만 분석 결과의 형식이 올바르지 않아 검증에 실패했습니다."
    ),
    ErrorCode.QUALITY_GATE_FAILED: (
        "AI가 분석 결과를 생성했지만 내용의 정확성 또는 필수 정보 검증을 통과하지 못했습니다."
    ),
    ErrorCode.TOKEN_BUDGET_EXCEEDED: (
        "이번 분석에 허용된 AI 사용량을 모두 썼습니다. 잠시 후 다시 시도해 주세요."
    ),
    ErrorCode.ANALYSIS_CANCELLED: (
        "분석이 중단되었습니다(사용자 취소 또는 서버 재시작). 다시 시도해 주세요."
    ),
    ErrorCode.UNKNOWN_ERROR: (
        "AI 분석 중 알 수 없는 오류가 발생했습니다. 다시 시도해 주세요."
    ),
}

ERROR_ACTIONS: dict[str, str] = {
    ErrorCode.MODEL_DECOMMISSIONED: "대체 모델로 다시 시도하거나 설정에서 모델을 변경하세요.",
    ErrorCode.MODEL_NOT_FOUND: "설정의 모델 이름을 확인한 뒤 다시 시도하세요.",
    ErrorCode.RATE_LIMITED: "1~2분 뒤 다시 시도하거나 다른 Provider를 선택하세요.",
    ErrorCode.PROVIDER_UNAVAILABLE: "잠시 후 다시 시도하세요.",
    ErrorCode.AUTHENTICATION_FAILED: "설정 → AI에서 API 키를 다시 저장하세요.",
    ErrorCode.PERMISSION_DENIED: "다른 모델을 선택하거나 계정 권한을 확인하세요.",
    ErrorCode.REQUEST_TIMEOUT: "다시 시도하세요. 반복되면 더 빠른 모델을 선택하세요.",
    ErrorCode.CONTEXT_LIMIT_EXCEEDED: "분석 범위를 줄이거나 다른 모델을 선택하세요.",
    ErrorCode.OUTPUT_TRUNCATED: "다시 시도하거나 출력 한도가 큰 모델을 선택하세요.",
    ErrorCode.INVALID_JSON: "다시 시도하세요. 반복되면 다른 모델을 선택하세요.",
    ErrorCode.SCHEMA_VALIDATION_FAILED: "다시 시도하거나 다른 모델을 선택하세요.",
    ErrorCode.QUALITY_GATE_FAILED: "결과를 직접 검토·수정하거나 다른 모델로 재분석하세요.",
    ErrorCode.TOKEN_BUDGET_EXCEEDED: "잠시 후 다시 시도하세요.",
    ErrorCode.ANALYSIS_CANCELLED: "다시 분석을 실행하세요.",
    ErrorCode.UNKNOWN_ERROR: "다시 시도하고, 반복되면 서버 로그를 확인하세요.",
}

# 사용자가 즉시 재시도해서 성공 가능성이 있는 코드.
RETRYABLE_CODES = frozenset(
    {
        ErrorCode.RATE_LIMITED,
        ErrorCode.PROVIDER_UNAVAILABLE,
        ErrorCode.REQUEST_TIMEOUT,
        ErrorCode.TOKEN_BUDGET_EXCEEDED,
        ErrorCode.OUTPUT_TRUNCATED,
        ErrorCode.INVALID_JSON,
    }
)

_KIND_TO_CODE = {
    ErrorKind.MODEL_GONE: ErrorCode.MODEL_DECOMMISSIONED,
    ErrorKind.AUTH: ErrorCode.AUTHENTICATION_FAILED,
    ErrorKind.CONTEXT: ErrorCode.CONTEXT_LIMIT_EXCEEDED,
    ErrorKind.RATE_LIMIT: ErrorCode.RATE_LIMITED,
    ErrorKind.TIMEOUT: ErrorCode.REQUEST_TIMEOUT,
    ErrorKind.SERVER: ErrorCode.PROVIDER_UNAVAILABLE,
    ErrorKind.TRUNCATED: ErrorCode.OUTPUT_TRUNCATED,
    ErrorKind.JSON_INVALID: ErrorCode.INVALID_JSON,
    ErrorKind.CONTENT_POLICY: ErrorCode.PERMISSION_DENIED,
}

_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|gsk_[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{10,}"
    r"|Bearer\s+[A-Za-z0-9._\-]+|api[_-]?key\s*[=:]\s*\S+)",
    re.IGNORECASE,
)
_PATH_PATTERN = re.compile(r"(/Users/[^\s\"']+|/home/[^\s\"']+|[A-Za-z]:\\\\[^\s\"']+)")


def redact(text: str, limit: int = 300) -> str:
    """기술 메시지에서 키·인증 헤더·로컬 경로를 지운다.

    클라이언트(개발자 상세)에만 쓰이며, 저장 파일에는 기록하지 않는다.
    """
    cleaned = _SECRET_PATTERN.sub("[redacted]", str(text or ""))
    cleaned = _PATH_PATTERN.sub("[path]", cleaned)
    return cleaned[:limit]


def error_code_for(kind: ErrorKind, exc: Optional[BaseException] = None) -> str:
    """내부 오류 분류를 클라이언트 오류 코드로 변환한다."""
    text = str(exc or "").lower()
    if kind is ErrorKind.MODEL_GONE:
        if "not found" in text or "does not exist" in text or "404" in text:
            return ErrorCode.MODEL_NOT_FOUND
        return ErrorCode.MODEL_DECOMMISSIONED
    if kind is ErrorKind.AUTH and ("403" in text or "permission" in text):
        return ErrorCode.PERMISSION_DENIED
    if kind is ErrorKind.BAD_REQUEST and "schema" in text:
        return ErrorCode.SCHEMA_VALIDATION_FAILED
    return _KIND_TO_CODE.get(kind, ErrorCode.UNKNOWN_ERROR)


def is_retryable_code(code: str) -> bool:
    return code in RETRYABLE_CODES


def user_message(code: str) -> str:
    return ERROR_USER_MESSAGES.get(code, ERROR_USER_MESSAGES[ErrorCode.UNKNOWN_ERROR])


# ---------------------------------------------------------------------------
# 표시 이름 (Provider / Model 분리)
# ---------------------------------------------------------------------------

_PROVIDER_LABELS = {
    "groq": "Groq",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "openrouter": "OpenRouter",
    "ollama": "Ollama",
    "pollinations": "Pollinations",
}

_MODEL_TOKEN_LABELS = {
    "gpt": "GPT",
    "oss": "OSS",
    "qwen": "Qwen",
    "llama": "Llama",
    "gemma": "Gemma",
    "deepseek": "DeepSeek",
    "claude": "Claude",
    "gemini": "Gemini",
    "sonnet": "Sonnet",
    "opus": "Opus",
    "haiku": "Haiku",
    "instruct": "Instruct",
    "preview": "Preview",
    "mini": "Mini",
    "flash": "Flash",
    "pro": "Pro",
    "fast": "Fast",
    "openai": "OpenAI",
}


def provider_display(provider: str) -> str:
    """`groq` → `Groq`. 모르는 Provider 는 원문 유지(사용 가능으로 단정하지 않음)."""
    return _PROVIDER_LABELS.get((provider or "").lower(), provider or "")


def model_display(model_id: str) -> str:
    """`openai/gpt-oss-120b` → `GPT-OSS 120B`.

    Provider 접두사(vendor)는 떼고, 토큰만 사람이 읽는 형태로 바꾼다.
    원문(model_id)은 항상 함께 내려주므로 표시 이름이 틀려도 정보 손실은 없다.
    """
    raw = (model_id or "").strip()
    if not raw:
        return ""
    short = raw.rsplit("/", 1)[-1]
    short = short.replace(":free", "").replace(":beta", "")
    tokens = []
    for part in re.split(r"[-_]", short):
        if not part:
            continue
        mapped = _MODEL_TOKEN_LABELS.get(part.lower())
        if mapped:
            tokens.append(mapped)
        elif re.fullmatch(r"[0-9.]+[A-Za-z]", part):  # 120b → 120B
            tokens.append(part.upper())
        else:
            tokens.append(part[:1].upper() + part[1:])

    # "GPT-OSS 120B" 처럼 영문 토큰 끼리는 하이픈, 숫자 앞은 공백으로 보기 좋게 만든다.
    rendered = ""
    for index, token in enumerate(tokens):
        if index == 0:
            rendered = token
        elif token[:1].isdigit() or tokens[index - 1][:1].isdigit():
            rendered += f" {token}"
        else:
            rendered += f"-{token}"
    return rendered or short


# ---------------------------------------------------------------------------
# 이벤트 / 호출 기록
# ---------------------------------------------------------------------------


@dataclass
class CallRecord:
    """AI 호출 1회(모델 후보 1개에 대한 시도)의 기록."""

    stage: str
    attempt: int
    provider: str
    model: str
    status: str = "running"  # running | ok | error | skipped
    error_code: str = ""
    fallback_reason: str = ""
    retry_after_seconds: Optional[float] = None
    duration_ms: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    technical: str = ""  # 저장하지 않음(메모리 전용)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "stage_label": STAGE_LABELS.get(self.stage, self.stage),
            "attempt": self.attempt,
            "provider": self.provider,
            "provider_display": provider_display(self.provider),
            "model_id": self.model,
            "model_display": model_display(self.model),
            "status": self.status,
            "error_code": self.error_code,
            "fallback_reason": self.fallback_reason,
            "retry_after_seconds": self.retry_after_seconds,
            "duration_ms": self.duration_ms,
        }


@dataclass
class StageState:
    stage_id: str
    label: str
    status: str = "pending"
    detail: str = ""
    provider: str = ""
    model: str = ""
    error_code: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        duration_ms = 0
        if self.started_at:
            end = self.finished_at or time.time()
            duration_ms = int((end - self.started_at) * 1000)
        return {
            "stage_id": self.stage_id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "provider": self.provider,
            "provider_display": provider_display(self.provider),
            "model_id": self.model,
            "model_display": model_display(self.model),
            "error_code": self.error_code,
            "duration_ms": duration_ms,
        }


def _new_stages() -> dict[str, StageState]:
    return {stage_id: StageState(stage_id, label) for stage_id, label in STAGE_DEFS}


@dataclass
class AnalysisRun:
    """AI 분석 요청 1회의 전체 상태. API·UI 가 읽는 단일 출처."""

    analysis_id: str
    repo_name: str = ""
    request_id: str = ""
    status: str = RUN_PENDING
    current_stage: str = ""
    requested_provider: str = ""
    requested_model: str = ""
    selected_provider: str = ""
    selected_model: str = ""
    effective_provider: str = ""
    effective_model: str = ""
    fallback_count: int = 0
    quality_verdict: str = ""
    error_summary: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    stages: dict[str, StageState] = field(default_factory=_new_stages)
    calls: list[CallRecord] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    dev_errors: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    # -- 상태 전이 -----------------------------------------------------
    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def cancelled(self) -> bool:
        return self.status == RUN_CANCELLED

    def _emit(self, event: dict[str, Any]) -> None:
        self.seq += 1
        event["seq"] = self.seq
        event["at"] = time.time()
        self.events.append(event)
        # 이벤트는 최근 200개만 유지(폴링 커서는 seq 기준이라 오래된 항목 삭제 무해).
        if len(self.events) > 200:
            self.events = self.events[-200:]

    def _stage(self, stage_id: str) -> StageState:
        if stage_id not in self.stages:
            self.stages[stage_id] = StageState(
                stage_id, STAGE_LABELS.get(stage_id, stage_id)
            )
        return self.stages[stage_id]

    def apply_event(self, event: dict[str, Any]) -> None:
        """AIService 가 보내는 이벤트를 상태에 반영한다."""
        if self.is_terminal:
            return  # 취소·완료 뒤 도착한 늦은 이벤트는 무시
        event_type = event.get("type", "")
        stage_id = str(event.get("stage", "") or "")
        if not stage_id and event_type != "stage_start":
            # 훅이 단계 정보를 생략한 경우 현재 단계에 귀속시킨다.
            stage_id = self.current_stage
        stage = self._stage(stage_id) if stage_id else None

        if event_type == "stage_start" and stage:
            stage.status = "running"
            stage.started_at = stage.started_at or time.time()
            self.current_stage = stage_id
            self.status = RUN_VALIDATING if stage_id == "quality" else RUN_RUNNING
            self._emit(event)
            return

        if event_type == "attempt" and stage:
            self.current_stage = stage_id
            attempt = int(event.get("attempt", 1) or 1)
            if attempt > 1:
                self.status = RUN_RETRYING
            elif self.status not in (RUN_FALLBACK, RUN_RETRYING):
                self.status = RUN_RUNNING
            provider = str(event.get("provider", ""))
            model = str(event.get("model", ""))
            if not self.selected_model:
                # 라우터가 처음 고른 모델 = Selected Model
                self.selected_provider, self.selected_model = provider, model
            self.calls.append(
                CallRecord(
                    stage=stage_id, attempt=attempt, provider=provider, model=model
                )
            )
            self._emit(event)
            return

        if event_type == "attempt_ok":
            self._close_call(
                stage_id, "ok", duration_ms=int(event.get("duration_ms", 0))
            )
            if stage:
                stage.status = "running"
                stage.provider = str(event.get("provider", ""))
                stage.model = str(event.get("model", ""))
            self.effective_provider = str(event.get("provider", ""))
            self.effective_model = str(event.get("model", ""))
            # 검증 단계가 아니면 다시 "분석 중"으로 돌아간다.
            if self.current_stage != "quality":
                self.status = RUN_RUNNING
            self._emit(event)
            return

        if event_type == "attempt_error":
            code = str(event.get("error_code", "") or ErrorCode.UNKNOWN_ERROR)
            self._close_call(
                stage_id,
                "error",
                error_code=code,
                retry_after=event.get("retry_after_seconds"),
                technical=str(event.get("technical", "")),
            )
            self.errors.append(
                _public_error(
                    code,
                    stage_id=stage_id,
                    provider=str(event.get("provider", "")),
                    model=str(event.get("model", "")),
                    retry_after_seconds=event.get("retry_after_seconds"),
                    request_id=self.request_id,
                )
            )
            self.dev_errors.append(
                {
                    "error_code": code,
                    "stage_id": stage_id,
                    "provider": str(event.get("provider", "")),
                    "model_id": str(event.get("model", "")),
                    "technical_message": redact(str(event.get("technical", ""))),
                    "at": time.time(),
                }
            )
            if stage:
                stage.error_code = code
            self.error_summary = user_message(code)
            self._emit(event)
            return

        if event_type == "fallback":
            self.fallback_count = int(
                event.get("fallback_count", self.fallback_count + 1)
            )
            self.status = RUN_FALLBACK
            self._emit(event)
            return

        if event_type == "stage_end" and stage:
            stage.status = str(event.get("status", stage.status))
            stage.detail = str(event.get("detail", ""))[:200]
            stage.provider = str(event.get("provider", stage.provider))
            stage.model = str(event.get("model", stage.model))
            stage.finished_at = time.time()
            self.current_stage = ""
            self._emit(event)
            return

        self._emit(event)

    def _close_call(
        self,
        stage_id: str,
        status: str,
        *,
        duration_ms: int = 0,
        error_code: str = "",
        retry_after: Any = None,
        technical: str = "",
    ) -> None:
        for record in reversed(self.calls):
            if record.stage == stage_id and record.status == "running":
                record.status = status
                record.error_code = error_code
                record.duration_ms = duration_ms or int(
                    (time.time() - record.started_at) * 1000
                )
                record.retry_after_seconds = (
                    float(retry_after) if retry_after is not None else None
                )
                record.finished_at = time.time()
                record.technical = technical
                return
        # 대응하는 attempt 이벤트가 없던 호출(직접 기록)도 버리지 않는다.
        self.calls.append(
            CallRecord(
                stage=stage_id,
                attempt=1,
                provider=self.effective_provider,
                model=self.effective_model,
                status=status,
                error_code=error_code,
                duration_ms=duration_ms,
                finished_at=time.time(),
            )
        )

    def fail(self, code: str, *, stage_id: str = "", message: str = "") -> None:
        """복구 불가 실패로 종결한다."""
        self.errors.append(
            _public_error(
                code,
                stage_id=stage_id or self.current_stage,
                provider=self.effective_provider or self.selected_provider,
                model=self.effective_model or self.selected_model,
                request_id=self.request_id,
            )
        )
        if message:
            self.error_summary = redact(message, 200)
        else:
            self.error_summary = user_message(code)
        self.status = (
            RUN_CANCELLED if code == ErrorCode.ANALYSIS_CANCELLED else RUN_FAILED
        )
        self.current_stage = ""
        self.completed_at = time.time()

    def cancel(self) -> None:
        if self.is_terminal:
            return
        self.fail(ErrorCode.ANALYSIS_CANCELLED)

    def finish(
        self,
        status: str,
        *,
        quality_verdict: str = "",
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        if self.cancelled:
            return  # 취소된 실행의 결과는 반영하지 않는다
        self.status = status if status in TERMINAL_STATUSES else RUN_FAILED
        self.quality_verdict = quality_verdict
        if payload is not None:
            self.payload = payload
        self.current_stage = ""
        self.completed_at = time.time()

    # -- 직렬화 --------------------------------------------------------
    @property
    def completed_stages(self) -> int:
        """끝났고 **사용 가능한 결과를 남긴** 단계 수.

        실패한 단계를 완료로 세면 "4/4 단계"와 실패 배지가 동시에 보여 진행률이 거짓말이 된다.
        """
        return sum(
            1
            for stage in self.stages.values()
            if stage.status in ("completed", "skipped", "partial")
        )

    def to_dict(self, *, include_dev: bool = False) -> dict[str, Any]:
        total = len(STAGE_DEFS)
        completed = self.completed_stages
        elapsed_ms = int(((self.completed_at or time.time()) - self.started_at) * 1000)
        data: dict[str, Any] = {
            "analysis_id": self.analysis_id,
            "request_id": self.request_id,
            "repo_name": self.repo_name,
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "current_stage": self.current_stage,
            "current_stage_label": STAGE_LABELS.get(self.current_stage, ""),
            "completed_stages": completed,
            "total_stages": total,
            "progress_percent": int(completed * 100 / total) if total else 0,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_ms": elapsed_ms,
            "requested_provider": self.requested_provider,
            "requested_provider_display": provider_display(self.requested_provider),
            "requested_model": self.requested_model,
            "requested_model_display": model_display(self.requested_model),
            "selected_provider": self.selected_provider,
            "selected_provider_display": provider_display(self.selected_provider),
            "selected_model": self.selected_model,
            "selected_model_display": model_display(self.selected_model),
            "effective_provider": self.effective_provider,
            "effective_provider_display": provider_display(self.effective_provider),
            "effective_model": self.effective_model,
            "effective_model_display": model_display(self.effective_model),
            "fallback_occurred": self.fallback_count > 0,
            "fallback_count": self.fallback_count,
            "quality_verdict": self.quality_verdict,
            "error_summary": self.error_summary,
            "stages": [
                self.stages[stage_id].to_dict()
                for stage_id, _ in STAGE_DEFS
                if stage_id in self.stages
            ],
            "calls": [call.to_dict() for call in self.calls],
            "errors": list(self.errors),
            "seq": self.seq,
        }
        if self.is_terminal and self.payload:
            data["payload"] = self.payload
        if include_dev:
            data["dev"] = {"errors": list(self.dev_errors)}
        return data

    def to_storage_dict(self) -> dict[str, Any]:
        """파일 저장용 — 기술 상세는 저장하지 않는다."""
        data = self.to_dict(include_dev=False)
        data["params"] = self.params
        data["payload"] = self.payload
        return data

    def events_since(self, cursor: int) -> list[dict[str, Any]]:
        return [event for event in self.events if int(event.get("seq", 0)) > cursor]


def _public_error(
    code: str,
    *,
    stage_id: str = "",
    provider: str = "",
    model: str = "",
    retry_after_seconds: Any = None,
    request_id: str = "",
) -> dict[str, Any]:
    """클라이언트에 내려도 안전한 오류 객체. 기술 상세는 포함하지 않는다."""
    retry_after = None
    if isinstance(retry_after_seconds, (int, float)):
        retry_after = float(retry_after_seconds)
    return {
        "error_code": code,
        "user_message": user_message(code),
        "provider": provider,
        "provider_display": provider_display(provider),
        "model_id": model,
        "model_display": model_display(model),
        "stage_id": stage_id,
        "stage_label": STAGE_LABELS.get(stage_id, stage_id),
        "retryable": is_retryable_code(code),
        "retry_after_seconds": retry_after,
        "request_id": request_id,
        "action": ERROR_ACTIONS.get(code, ""),
        "occurred_at": time.time(),
    }


# ---------------------------------------------------------------------------
# 실행 저장소
# ---------------------------------------------------------------------------


class AnalysisRunRegistry:
    """최근 분석 실행을 메모리 + 파일에 보관한다.

    단일 프로세스 로컬 도구라 Redis 같은 공유 저장소를 두지 않는다.
    파일은 사용자 데이터 디렉터리(0o600)에 쓰고, 최근 `max_runs` 건만 유지한다.
    """

    FILE_NAME = "ai_analysis_runs.json"

    def __init__(self, path: Optional[Path] = None, max_runs: int = 20) -> None:
        self._explicit_path = path
        self.max_runs = max_runs
        self._runs: dict[str, AnalysisRun] = {}
        self._lock = threading.RLock()
        self._loaded = False

    # -- 경로 ----------------------------------------------------------
    def _path(self) -> Path:
        if self._explicit_path is not None:
            return self._explicit_path
        from devfolio.core import storage

        return Path(storage.DEVFOLIO_DATA_DIR) / self.FILE_NAME

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self._path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("분석 실행 기록을 읽지 못했습니다: %s", exc)
            return
        for item in raw.get("runs", []) if isinstance(raw, dict) else []:
            try:
                run = self._from_storage_dict(item)
            except (TypeError, KeyError, ValueError) as exc:
                logger.debug("분석 실행 기록 1건을 건너뜁니다: %s", exc)
                continue
            self._runs[run.analysis_id] = run

    def _from_storage_dict(self, item: dict[str, Any]) -> AnalysisRun:
        run = AnalysisRun(
            analysis_id=str(item["analysis_id"]),
            repo_name=str(item.get("repo_name", "")),
            request_id=str(item.get("request_id", "")),
            status=str(item.get("status", RUN_FAILED)),
            requested_provider=str(item.get("requested_provider", "")),
            requested_model=str(item.get("requested_model", "")),
            selected_provider=str(item.get("selected_provider", "")),
            selected_model=str(item.get("selected_model", "")),
            effective_provider=str(item.get("effective_provider", "")),
            effective_model=str(item.get("effective_model", "")),
            fallback_count=int(item.get("fallback_count", 0) or 0),
            quality_verdict=str(item.get("quality_verdict", "")),
            error_summary=str(item.get("error_summary", "")),
            started_at=float(item.get("started_at", time.time())),
            completed_at=item.get("completed_at"),
            errors=list(item.get("errors", [])),
            payload=dict(item.get("payload") or {}),
            params=dict(item.get("params") or {}),
            seq=int(item.get("seq", 0) or 0),
        )
        for stage_item in item.get("stages", []):
            stage_id = str(stage_item.get("stage_id", ""))
            if not stage_id:
                continue
            run.stages[stage_id] = StageState(
                stage_id=stage_id,
                label=str(
                    stage_item.get("label", STAGE_LABELS.get(stage_id, stage_id))
                ),
                status=str(stage_item.get("status", "pending")),
                detail=str(stage_item.get("detail", "")),
                provider=str(stage_item.get("provider", "")),
                model=str(stage_item.get("model_id", "")),
                error_code=str(stage_item.get("error_code", "")),
            )
        for call_item in item.get("calls", []):
            run.calls.append(
                CallRecord(
                    stage=str(call_item.get("stage", "")),
                    attempt=int(call_item.get("attempt", 1) or 1),
                    provider=str(call_item.get("provider", "")),
                    model=str(call_item.get("model_id", "")),
                    status=str(call_item.get("status", "ok")),
                    error_code=str(call_item.get("error_code", "")),
                    fallback_reason=str(call_item.get("fallback_reason", "")),
                    retry_after_seconds=call_item.get("retry_after_seconds"),
                    duration_ms=int(call_item.get("duration_ms", 0) or 0),
                )
            )
        # 재시작 전에 진행 중이던 실행은 완료로 보이면 안 된다.
        if run.status not in TERMINAL_STATUSES:
            run.status = RUN_CANCELLED
            run.current_stage = ""
            run.error_summary = user_message(ErrorCode.ANALYSIS_CANCELLED)
            run.errors.append(
                _public_error(
                    ErrorCode.ANALYSIS_CANCELLED,
                    provider=run.effective_provider or run.selected_provider,
                    model=run.effective_model or run.selected_model,
                    request_id=run.request_id,
                )
            )
            run.completed_at = run.completed_at or time.time()
        return run

    # -- CRUD ----------------------------------------------------------
    def create(
        self,
        *,
        repo_name: str,
        params: dict[str, Any],
        requested_provider: str = "",
        requested_model: str = "",
        request_id: str = "",
    ) -> AnalysisRun:
        run = AnalysisRun(
            analysis_id=uuid.uuid4().hex,
            repo_name=repo_name,
            request_id=request_id or uuid.uuid4().hex[:12],
            requested_provider=requested_provider,
            requested_model=requested_model,
            params=dict(params),
        )
        with self._lock:
            self._ensure_loaded()
            self._runs[run.analysis_id] = run
            self._trim()
        return run

    def get(self, analysis_id: str) -> Optional[AnalysisRun]:
        with self._lock:
            self._ensure_loaded()
            return self._runs.get(analysis_id)

    def running_for_repo(self, repo_path: str) -> Optional[AnalysisRun]:
        normalized = _normalize_repo_path(repo_path)
        with self._lock:
            self._ensure_loaded()
            for run in self._runs.values():
                if run.is_terminal:
                    continue
                if _normalize_repo_path(run.params.get("repo_path", "")) == normalized:
                    return run
        return None

    def save(self, run: AnalysisRun) -> None:
        with self._lock:
            self._ensure_loaded()
            self._runs[run.analysis_id] = run
            self._trim()
            self._save_locked()

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            self._ensure_loaded()
            ordered = sorted(
                self._runs.values(), key=lambda r: r.started_at, reverse=True
            )
            return [run.to_dict() for run in ordered[:limit]]

    def clear(self) -> None:
        """테스트·수동 정리용."""
        with self._lock:
            self._runs.clear()
            self._loaded = True
            self._save_locked()

    # -- 내부 ----------------------------------------------------------
    def _trim(self) -> None:
        if len(self._runs) <= self.max_runs:
            return
        ordered = sorted(self._runs.values(), key=lambda r: r.started_at)
        for run in ordered[: len(self._runs) - self.max_runs]:
            self._runs.pop(run.analysis_id, None)

    def _save_locked(self) -> None:
        path = self._path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "runs": [
                    run.to_storage_dict()
                    for run in sorted(
                        self._runs.values(), key=lambda r: r.started_at, reverse=True
                    )
                ]
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:  # Windows 등 권한 미지원 환경
                pass
            tmp.replace(path)
        except OSError as exc:
            logger.warning("분석 실행 기록을 저장하지 못했습니다: %s", exc)


def _normalize_repo_path(path: str) -> str:
    return str(path or "").strip().rstrip("/")


_DEFAULT_REGISTRY: Optional[AnalysisRunRegistry] = None


def get_run_registry() -> AnalysisRunRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = AnalysisRunRegistry()
    return _DEFAULT_REGISTRY

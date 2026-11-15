"""AI 호출 신뢰성 계층 — 오류 분류, 모델 상태(Circuit Breaker), 시간 예산, 백오프.

[Spring 비교]
  Resilience4j 의 CircuitBreaker + Retry + TimeLimiter 를 한 곳에 모은 얇은 계층이다.
  프레임워크나 새 의존성 없이 표준 라이브러리만 사용한다.

설계 원칙 (LiteLLM Router 문서와 동일한 시맨틱):
  - 4xx 중 401/403/408/409/429 를 제외한 응답과 not-found 는 재시도하지 않는다.
  - 모델 폐기(`model_decommissioned`)는 영구 차단한다. Cooldown 후에도 재시도하지 않는다.
  - 일시 장애는 Cooldown(기본 300초) 동안만 차단하고, 이후 다시 후보에 넣는다.
  - 재시도는 지수 백오프 + 지터를 쓰되 총 시간 예산을 넘지 않는다.
  - 재시도 제어 지점은 애플리케이션 한 곳뿐이다 (litellm 내부 재시도는 끈다).
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from devfolio.log import get_logger

logger = get_logger(__name__)


class ErrorKind(str, Enum):
    """AI 호출 실패의 성격. 재시도·차단 정책이 여기서 갈린다."""

    MODEL_GONE = "model_gone"  # 폐기·미존재 — 영구 차단
    AUTH = "auth"  # 401/403 — 같은 자격증명 반복 금지
    CONTEXT = "context"  # 컨텍스트 초과 — 입력 축소 또는 긴 컨텍스트 모델
    BAD_REQUEST = "bad_request"  # 400 파라미터 오류 — 재시도 무의미
    CONTENT_POLICY = "content_policy"  # 정책 위반 — 모델 전환으로 우회하지 않음
    RATE_LIMIT = "rate_limit"  # 429 — Retry-After/예산 확인 후 재시도
    TIMEOUT = "timeout"  # 408/타임아웃 — 제한 재시도
    SERVER = "server"  # 5xx — 백오프 후 재시도
    TRUNCATED = "truncated"  # finish_reason=length — 잘린 출력
    JSON_INVALID = "json_invalid"  # 스키마·파싱 실패
    UNKNOWN = "unknown"


# 영구 차단: Cooldown 이 지나도 같은 모델을 다시 부르지 않는다.
PERMANENT_KINDS = frozenset(
    {
        ErrorKind.MODEL_GONE,
        ErrorKind.AUTH,
        ErrorKind.BAD_REQUEST,
        ErrorKind.CONTENT_POLICY,
        ErrorKind.CONTEXT,
    }
)

# 일시 장애: 같은 모델을 백오프 후 한 번 더 시도할 수 있다.
# LiteLLM Router 와 같은 기준 — 4xx(401/403/408/409/429 제외)·not-found·검증 실패는 재시도하지 않는다.
RETRYABLE_KINDS = frozenset({ErrorKind.RATE_LIMIT, ErrorKind.TIMEOUT, ErrorKind.SERVER})

# Provider 자체를 쓸 수 없다고 판단하는 종류. 이 경우 다음 Provider 로 즉시 넘어간다.
PROVIDER_LEVEL_KINDS = frozenset({ErrorKind.AUTH, ErrorKind.MODEL_GONE})


def classify_error(exc: BaseException) -> ErrorKind:
    """예외 객체를 정책 판단용 종류로 분류한다.

    오류 클래스 이름과 메시지만 본다. 문구는 Provider 마다 다르므로
    LiteLLM 예외 이름 + Provider 고유 코드(`model_decommissioned` 등)를 함께 확인한다.
    """
    err_class = type(exc).__name__
    message = str(exc)
    text = f"{err_class} {message}".lower()

    # 폐기된 모델 — 영구. not-found 보다 먼저 봐야 한다(둘 다 404 계열).
    if "model_decommissioned" in text or "decommissioned" in text:
        return ErrorKind.MODEL_GONE
    if "notfounderror" in text or "does not exist" in text or "model not found" in text:
        return ErrorKind.MODEL_GONE

    # 인증·권한 — 같은 자격증명으로 반복해도 결과가 같다.
    if (
        "authenticationerror" in text
        or "permissiondenied" in text
        or "invalid api key" in text
        or "unauthorized" in text
        or "forbidden" in text
        or "access denied" in text
    ):
        return ErrorKind.AUTH

    # 할당량·속도 제한 — 재시도 가치가 있는 대표적인 오류.
    # Provider 마다 문구가 다르다: Groq "Rate limit reached for model ...",
    # pollinations "Free limit reached: 1 reply every 45 seconds per IP" (litellm 은 APIError 로 올린다).
    if (
        "ratelimiterror" in text
        or "rate limit" in text
        or "ratelimit" in text
        or "resource_exhausted" in text
        or "free limit" in text
        or "too many requests" in text
        or "retry after" in text
        or "429" in text
    ):
        return ErrorKind.RATE_LIMIT

    if "timeout" in text or "timed out" in text or " 408" in f" {text}":
        return ErrorKind.TIMEOUT

    if (
        "contextwindow" in text
        or "context length" in text
        or "maximum context" in text
        or "too many tokens" in text
    ):
        return ErrorKind.CONTEXT

    if "contentpolicy" in text or "content policy" in text or "safety" in text:
        return ErrorKind.CONTENT_POLICY

    if (
        "internalservererror" in text
        or "serviceunavailable" in text
        or "badgateway" in text
        or "apiconnectionerror" in text
        or "connection error" in text
    ):
        return ErrorKind.SERVER

    # 우리가 직접 던진 오류 — 원인을 이미 알고 있다.
    if "잘렸" in message or "truncated" in text:
        return ErrorKind.TRUNCATED
    if "빈 응답" in message or "오류 문구" in message:
        return ErrorKind.UNKNOWN
    if "badrequesterror" in text or "invalid_request" in text:
        return ErrorKind.BAD_REQUEST

    return ErrorKind.UNKNOWN


def is_retryable(kind: ErrorKind) -> bool:
    return kind in RETRYABLE_KINDS


def is_permanent(kind: ErrorKind) -> bool:
    return kind in PERMANENT_KINDS


@dataclass(frozen=True)
class ReliabilitySettings:
    """환경변수로 조정 가능한 신뢰성 정책 값."""

    time_budget_seconds: float = 90.0  # AI 호출 전체(모델·Provider 전환 포함) 시간 예산
    model_retries: int = 1  # 같은 모델에서의 추가 재시도 횟수
    max_models: int = 3  # Provider 당 후보 모델 수 상한
    cooldown_seconds: float = 300.0  # 일시 장애 모델을 쉬게 하는 시간
    max_backoff_seconds: float = 8.0  # 백오프 상한
    provider_fallback: bool = True  # Provider 장애 시 다른 Provider 로 전환할지
    # Provider 분당 토큰 예산. 0 이면 비활성. 값은 계정 정책에 맞춰 사용자가 정한다.
    provider_tpm: int = 0
    allow_third_party_fallback: bool = (
        True  # 키 없는 내장 Provider(pollinations) 허용 여부
    )

    @classmethod
    def from_env(cls) -> "ReliabilitySettings":
        defaults = cls()
        return cls(
            # 0 은 "재시도 없음"처럼 의미 있는 값이므로 허용하고, 예산만 최소 1초로 눌러 둔다.
            time_budget_seconds=max(
                1.0,
                _env_float("DEVFOLIO_AI_TIME_BUDGET", defaults.time_budget_seconds),
            ),
            model_retries=_env_int("DEVFOLIO_AI_MODEL_RETRIES", defaults.model_retries),
            max_models=_env_int("DEVFOLIO_AI_MAX_MODELS", defaults.max_models),
            cooldown_seconds=_env_float(
                "DEVFOLIO_AI_COOLDOWN", defaults.cooldown_seconds
            ),
            max_backoff_seconds=_env_float(
                "DEVFOLIO_AI_MAX_BACKOFF", defaults.max_backoff_seconds
            ),
            provider_fallback=_env_bool(
                "DEVFOLIO_AI_PROVIDER_FALLBACK", defaults.provider_fallback
            ),
            provider_tpm=_env_int("DEVFOLIO_AI_PROVIDER_TPM", defaults.provider_tpm),
            allow_third_party_fallback=_env_bool(
                "DEVFOLIO_AI_ALLOW_THIRD_PARTY", defaults.allow_third_party_fallback
            ),
        )


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s 값이 숫자가 아니어서 기본값을 사용합니다: %r", name, raw)
        return default
    return value if value >= 0 else default


def _env_int(name: str, default: int) -> int:
    value = _env_float(name, float(default))
    return max(0, int(value))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Budget:
    """AI 실행 1회의 시간 예산. 재시도·대기가 예산을 넘지 않게 막는다."""

    seconds: float = 90.0
    started_at: float = field(default_factory=time.monotonic)
    attempts: int = 0

    def remaining(self) -> float:
        return max(0.0, self.seconds - (time.monotonic() - self.started_at))

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def can_wait(self, seconds: float) -> bool:
        """대기 후에도 최소 1초의 호출 여유가 남는지."""
        return self.remaining() > seconds + 1.0


def backoff_delay(
    attempt: int,
    *,
    base: float = 1.0,
    cap: float = 8.0,
    retry_after: Optional[float] = None,
) -> float:
    """지수 백오프 + 지터. Retry-After 가 있으면 그 값을 존중한다."""
    if retry_after is not None and retry_after > 0:
        return min(retry_after, cap)
    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    # 지터: 동시에 여러 요청이 같은 시점에 몰리지 않게 한다.
    return delay * (0.5 + random.random() / 2)


_RETRY_AFTER_PATTERN = re.compile(r"retry\s+after\s+(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def parse_retry_after(exc: BaseException) -> Optional[float]:
    """예외에서 Retry-After(초)를 뽑아낸다.

    ① 예외 속성/응답 헤더(표준) → ② 본문 문구("Retry after 18s", pollinations).
    헤더가 없으면 포기하지 않고 본문을 본다 — pollinations 는 헤더 대신 문구로 알린다.
    """
    for attr in ("retry_after", "retry_after_seconds"):
        value = getattr(exc, attr, None)
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        try:
            raw = headers.get("retry-after") or headers.get("Retry-After")
        except Exception:  # noqa: BLE001 — 헤더 접근 실패는 무시
            raw = None
        if raw:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    match = _RETRY_AFTER_PATTERN.search(str(exc))
    if match:
        return float(match.group(1))
    return None


@dataclass
class HealthRecord:
    kind: str
    reason: str
    marked_at: float
    permanent: bool
    # 이 기록만의 Cooldown 길이. None 이면 저장소 기본값을 쓴다.
    # 429 의 Retry-After 처럼 Provider 가 알려준 대기 시간을 그대로 반영할 때 쓴다.
    ttl: Optional[float] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "marked_at": self.marked_at,
            "permanent": self.permanent,
            "ttl": self.ttl,
        }


class ModelHealthStore:
    """모델별 Circuit Breaker.

    상태는 CLOSED(정상) / OPEN(차단) 두 가지로 단순화한다. HALF_OPEN 은
    "Cooldown 이 지나 차단이 풀린 상태"로 표현한다 — 다음 시도가 실패하면 다시 OPEN 이 된다.
    영구 종료 모델은 프로세스가 재시작돼도 계속 차단되도록 파일에 남긴다.
    """

    FILE_NAME = "ai_model_health.json"

    def __init__(
        self,
        *,
        cooldown_seconds: float = 300.0,
        path: Optional[Path] = None,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._path = path
        self._records: dict[str, HealthRecord] = {}
        self._loaded = False

    # -- 저장소 ---------------------------------------------------------
    def _file(self) -> Optional[Path]:
        if self._path is not None:
            return self._path
        try:
            from devfolio.core.storage import DEVFOLIO_DATA_DIR

            return DEVFOLIO_DATA_DIR / self.FILE_NAME
        except Exception:  # noqa: BLE001 — 저장 경로를 못 찾으면 메모리만 사용
            return None

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self._file()
        if path is None or not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 손상된 캐시는 무시하고 새로 시작
            return
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            try:
                self._records[str(key)] = HealthRecord(
                    kind=str(value.get("kind", "unknown")),
                    reason=str(value.get("reason", ""))[:200],
                    marked_at=float(value.get("marked_at", 0.0)),
                    permanent=bool(value.get("permanent", False)),
                )
            except (TypeError, ValueError):
                continue

    def _save(self) -> None:
        path = self._file()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {key: rec.to_dict() for key, rec in self._records.items()}
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001 — 상태 저장 실패가 분석을 막지는 않는다
            logger.debug("모델 상태 저장 실패", exc_info=True)

    # -- 조회/갱신 ------------------------------------------------------
    @staticmethod
    def key(provider_name: str, model_name: str) -> str:
        return f"{provider_name}::{model_name}"

    def blocked(self, key: str) -> bool:
        return self.remaining(key) > 0

    def remaining(self, key: str) -> float:
        """차단이 플러질 때까지 남은 초. 0 이면 차단 아님.

        permanent 기록은 아주 큰 값을 돌려준다(사실상 해제되지 않음).
        """
        self._load()
        record = self._records.get(key)
        if record is None:
            return 0.0
        if record.permanent:
            return float("inf")
        ttl = record.ttl if record.ttl is not None else self.cooldown_seconds
        elapsed = time.time() - record.marked_at
        if elapsed >= ttl:
            # Cooldown 종료 → 다시 시도 가능(HALF_OPEN).
            self._records.pop(key, None)
            self._save()
            return 0.0
        return ttl - elapsed

    # -- Provider 단위 차단 --------------------------------------------
    # 레이트 리밋은 모델이 아니라 계정·IP 단위로 걸리는 경우가 많다.
    # Groq 은 조직 단위로 제한하고, pollinations 는 IP 단위로 제한한다(로그 문구 기준).
    # 따라서 모델을 바꿔 가며 같은 한도를 반복 소모하지 않도록 Provider 도 차단한다.
    def block_provider(
        self, provider_name: str, seconds: Optional[float], reason: str
    ) -> None:
        self._load()
        ttl = seconds if seconds and seconds > 0 else self.cooldown_seconds
        key = self.key(provider_name, PROVIDER_WILDCARD)
        self._records[key] = HealthRecord(
            kind=ErrorKind.RATE_LIMIT.value,
            reason=reason[:200],
            marked_at=time.time(),
            permanent=False,
            ttl=ttl,
        )
        self._save()
        logger.warning(
            "Provider 차단: %s (%.0f초, reason=%.120s)", provider_name, ttl, reason
        )

    def provider_cooldown_remaining(self, provider_name: str) -> float:
        return self.remaining(self.key(provider_name, PROVIDER_WILDCARD))

    def block(self, key: str, kind: ErrorKind, reason: str) -> None:
        self._load()
        permanent = is_permanent(kind)
        self._records[key] = HealthRecord(
            kind=kind.value,
            reason=reason[:200],
            marked_at=time.time(),
            permanent=permanent,
        )
        self._save()
        logger.warning(
            "모델 차단: %s (kind=%s, permanent=%s, reason=%s)",
            key,
            kind.value,
            permanent,
            reason[:120],
        )

    def clear(self, key: str) -> None:
        self._load()
        if self._records.pop(key, None) is not None:
            self._save()

    def snapshot(self) -> dict[str, dict[str, object]]:
        self._load()
        return {key: rec.to_dict() for key, rec in self._records.items()}

    def reset(self) -> None:
        """테스트·수동 복구용. 모든 차단 상태를 지운다."""
        self._records.clear()
        self._loaded = True
        self._save()


PROVIDER_WILDCARD = "*"


def estimate_tokens(messages: list[dict], max_tokens: Optional[int] = None) -> int:
    """요청 1회의 토큰 사용량을 보수적으로 어림한다.

    정확한 토크나이저를 추가하지 않는다(의존성·비용). 문자 수 / 3 은 한국어·코드 혼합에서
    실제보다 조금 크게 나오는 편이라, 예산 확인용으로는 안전한 쪽이다.
    출력은 모델이 실제로 다 쓸 수 있는 양(max_tokens)을 예약한다.
    """
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
    return prompt_chars // 3 + (max_tokens or 0)


class ProviderTokenWindow:
    """Provider 별 분당 토큰 예산(슬라이딩 윈도우).

    capacity 가 0 이면 비활성(기본). 제한값은 Provider 정책마다 다르고 계정마다 다를 수
    있으므로 코드에 상수로 박지 않고 `DEVFOLIO_AI_PROVIDER_TPM` 으로 설정한다.
    상태는 프로세스 로컬이다 — 로컬 단일 프로세스 도구라 Redis 같은 공유 저장소는 불필요하다.
    """

    def __init__(self, capacity: int, window_seconds: float = 60.0) -> None:
        self.capacity = max(0, int(capacity))
        self.window_seconds = window_seconds
        self._events: list[tuple[float, int]] = []

    @property
    def enabled(self) -> bool:
        return self.capacity > 0

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self._events = [(ts, tok) for ts, tok in self._events if ts > cutoff]

    def used(self) -> int:
        self._prune(time.monotonic())
        return sum(tokens for _, tokens in self._events)

    def wait_seconds(self, tokens: int = 0) -> float:
        """지금 요청을 보내려면 얼마나 기다려야 하는가. 0 이면 바로 가능."""
        if not self.enabled:
            return 0.0
        now = time.monotonic()
        self._prune(now)
        if sum(t for _, t in self._events) + tokens <= self.capacity:
            return 0.0
        # 가장 오래된 이벤트가 윈도우를 벗어나면 다시 여유가 생긴다.
        if not self._events:
            return 0.0
        oldest = min(ts for ts, _ in self._events)
        return max(0.0, self.window_seconds - (now - oldest))

    def reserve(self, tokens: int) -> None:
        if not self.enabled:
            return
        self._events.append((time.monotonic(), max(0, tokens)))

    def reset(self) -> None:
        self._events.clear()


_TOKEN_WINDOWS: dict[str, ProviderTokenWindow] = {}


def get_token_window(
    provider_name: str, settings: "ReliabilitySettings"
) -> ProviderTokenWindow:
    window = _TOKEN_WINDOWS.get(provider_name)
    if window is None or window.capacity != settings.provider_tpm:
        window = ProviderTokenWindow(settings.provider_tpm)
        _TOKEN_WINDOWS[provider_name] = window
    return window


def reset_token_windows() -> None:
    _TOKEN_WINDOWS.clear()


_DEFAULT_STORE: Optional[ModelHealthStore] = None


def get_health_store(
    settings: Optional[ReliabilitySettings] = None,
) -> ModelHealthStore:
    """프로세스 공용 상태 저장소. 최초 호출 시 설정에서 Cooldown 을 읽는다."""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        resolved = settings or ReliabilitySettings.from_env()
        _DEFAULT_STORE = ModelHealthStore(cooldown_seconds=resolved.cooldown_seconds)
    return _DEFAULT_STORE


def reset_health_store() -> None:
    """테스트에서 전역 상태를 초기화한다."""
    global _DEFAULT_STORE
    _DEFAULT_STORE = None


def filter_candidates(
    provider_name: str,
    candidates: list[str],
    *,
    store: Optional[ModelHealthStore] = None,
    limit: Optional[int] = None,
) -> list[str]:
    """차단된 모델을 빼고 후보 순서를 유지한다."""
    active_store = store or get_health_store()
    available = [
        model
        for model in candidates
        if not active_store.blocked(ModelHealthStore.key(provider_name, model))
    ]
    if limit is not None:
        return available[: max(0, limit)]
    return available

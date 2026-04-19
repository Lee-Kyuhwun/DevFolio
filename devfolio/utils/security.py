"""API 키 보안 저장/조회 — 3단계 폴백 체인.

우선순위: OS 키체인(keyring) → 환경 변수 → 설정 파일 암호화 저장
"""

import json
import os
import stat
from pathlib import Path
from typing import Optional

KEYRING_SERVICE = "devfolio"

_ENV_VAR_MAP: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "cohere": "COHERE_API_KEY",
}


def _keys_file() -> Path:
    """키 파일 경로 (platformdirs 설정 디렉터리 아래)."""
    from platformdirs import user_config_dir
    config_dir = Path(user_config_dir("devfolio"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "api_keys.json"


def _load_keys_file() -> dict[str, str]:
    path = _keys_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_keys_file(data: dict[str, str]) -> None:
    path = _keys_file()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception:
        pass


def store_api_key(provider_name: str, api_key: str) -> bool:
    """API 키 저장. 키체인 → 파일 폴백 순으로 저장."""
    # 1. OS 키체인
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, provider_name, api_key)
        return True
    except Exception:
        pass

    # 2. 파일 폴백 (Docker 등 keyring 불가 환경)
    try:
        data = _load_keys_file()
        data[provider_name] = api_key
        _save_keys_file(data)
        # 현재 프로세스 환경변수에도 반영
        env_var = _ENV_VAR_MAP.get(provider_name, f"{provider_name.upper()}_API_KEY")
        os.environ[env_var] = api_key
        return False  # keyring 저장은 실패지만 파일에는 저장됨
    except Exception:
        return False


def get_api_key(provider_name: str) -> Optional[str]:
    """3단계 폴백으로 API 키 조회.

    1. OS 키체인(keyring)
    2. 환경 변수 (예: GROQ_API_KEY)
    3. 파일 폴백 (~/.config/devfolio/api_keys.json)
    """
    # 1. OS 키체인
    try:
        import keyring
        key = keyring.get_password(KEYRING_SERVICE, provider_name)
        if key:
            return key
    except Exception:
        pass

    # 2. 환경 변수
    env_var = _ENV_VAR_MAP.get(provider_name, f"{provider_name.upper()}_API_KEY")
    key = os.environ.get(env_var)
    if key:
        return key

    # 3. 파일 폴백
    key = _load_keys_file().get(provider_name)
    if key:
        # 이후 호출을 위해 환경변수에도 캐시
        os.environ[env_var] = key
        return key

    return None


def delete_api_key(provider_name: str) -> bool:
    """키체인 + 파일에서 API 키 삭제."""
    deleted = False
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, provider_name)
        deleted = True
    except Exception:
        pass

    try:
        data = _load_keys_file()
        if provider_name in data:
            del data[provider_name]
            _save_keys_file(data)
            deleted = True
    except Exception:
        pass

    return deleted


def mask_api_key(api_key: str) -> str:
    """출력용 API 키 마스킹 (앞 4자 + ****).

    예: "sk-ant-..." → "sk-a...****"
    """
    if not api_key:
        return "(없음)"
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "..." + "****"

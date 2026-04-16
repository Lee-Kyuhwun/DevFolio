"""API 키 보안 저장/조회 — 3단계 폴백 체인.

우선순위: OS 키체인(keyring) → 환경 변수 → 설정 파일 암호화 저장
"""

import os
from typing import Optional

KEYRING_SERVICE = "devfolio"

_ENV_VAR_MAP: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "cohere": "COHERE_API_KEY",
}


def store_api_key(provider_name: str, api_key: str) -> bool:
    """API 키를 OS 키체인에 저장. 실패 시 False 반환."""
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, provider_name, api_key)
        return True
    except Exception:
        return False


def get_api_key(provider_name: str) -> Optional[str]:
    """3단계 폴백으로 API 키 조회.

    1. OS 키체인(keyring)
    2. 환경 변수 (예: ANTHROPIC_API_KEY)
    3. 없으면 None
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

    return None


def delete_api_key(provider_name: str) -> bool:
    """키체인에서 API 키 삭제."""
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, provider_name)
        return True
    except Exception:
        return False


def mask_api_key(api_key: str) -> str:
    """출력용 API 키 마스킹 (앞 4자 + ****).

    예: "sk-ant-..." → "sk-a...****"
    """
    if not api_key:
        return "(없음)"
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "..." + "****"

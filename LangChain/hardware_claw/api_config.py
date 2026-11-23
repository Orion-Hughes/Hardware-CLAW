"""DeepSeek configuration. Importing this module does not read keys or call APIs."""
import getpass
import os
from pathlib import Path

from langchain_deepseek import ChatDeepSeek
from . import limits

KEY_FILE = Path(__file__).resolve().parents[1] / "DS_Api.txt"
DEFAULT_MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"


class ApiConfigError(ValueError):
    """Configuration error with a credential-free message."""


def load_api_key(*, ask_key: bool = False) -> str:
    """Prefer project key file, then environment, then optional hidden input.

    An existing but invalid file fails explicitly rather than using another key.
    """
    if KEY_FILE.exists():
        try:
            key = KEY_FILE.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError):
            raise ApiConfigError("Cannot read DS_Api.txt; save it as UTF-8 plain text.") from None
        if not key or any(char.isspace() for char in key):
            raise ApiConfigError("DS_Api.txt must contain only one non-empty API key, without labels or spaces.")
        return key
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and ask_key:
        key = getpass.getpass("DeepSeek API key (hidden): ").strip()
    if not key:
        raise ApiConfigError("Put your key in LangChain/DS_Api.txt, or set DEEPSEEK_API_KEY.")
    return key


def create_model(*, ask_key: bool = False, max_tokens: int = limits.COORDINATOR_OUTPUT_TOKENS):
    """Construct the client; actual API traffic begins when the agent runs."""
    return ChatDeepSeek(
        model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
        api_key=load_api_key(ask_key=ask_key),
        api_base=BASE_URL,
        timeout=limits.API_TIMEOUT_SECONDS,
        max_retries=0,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "disabled"}},
    )

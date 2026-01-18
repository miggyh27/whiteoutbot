import os
import ssl

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None

_ENV_LOADED = False


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if load_dotenv:
        load_dotenv()
    _ENV_LOADED = True


def _get_env(name: str, default: str | None = None) -> str | None:
    _load_env()
    return os.getenv(name, default)


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = _get_env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_discord_token() -> str | None:
    return _get_env("DISCORD_BOT_TOKEN")


def should_write_token_file() -> bool:
    return _get_bool_env("WOS_WRITE_TOKEN_FILE", False)


def get_wos_secret() -> str:
    return _get_env("WOS_API_SECRET", "tB87#kPtkxqOS2")


def get_gift_api_url() -> str:
    return _get_env(
        "WOS_GIFT_API_URL",
        "https://gift-code-api.whiteout-bot.com/giftcode_api.php",
    )


def get_gift_api_key() -> str:
    return _get_env("WOS_GIFT_API_KEY", "super_secret_bot_token_nobody_will_ever_find")


def use_gift_api_hmac() -> bool:
    return _get_bool_env("WOS_GIFT_API_HMAC", False)


def get_admin_channel_id() -> int | None:
    value = _get_env("WOS_ADMIN_CHANNEL_ID")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def is_insecure_ssl_enabled() -> bool:
    return _get_bool_env("WOS_INSECURE_SSL", False)


def get_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if is_insecure_ssl_enabled():
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def get_requests_verify() -> bool:
    return not is_insecure_ssl_enabled()

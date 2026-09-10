import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

def _value(name: str, default: str = "") -> str:
    raw = os.getenv(name)

    if raw is None:
        return default

    raw = raw.strip()

    return raw if raw else default

def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "si",
        "sí",
    }

def _int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    return int(raw.strip())


def _path(name: str, default: str) -> str:
    value = _value(name, default)
    path = Path(value)

    if path.is_absolute():
        return str(path)

    return str((ROOT / path).resolve())


def settings():
    load_dotenv(ROOT / ".env")

    app_env = _value("APP_ENV", "development").lower()

    return {
        "APP_ENV": app_env,
        "AUTH_ENABLED": _bool("AUTH_ENABLED", False),
        "SSO_ISSUER": _value("SSO_ISSUER", "calco-intranet",),
        "SSO_AUDIENCE": _value("SSO_AUDIENCE", "inventarios-uno-a-uno",),
        "SSO_PUBLIC_KEY_PATH": _value("SSO_PUBLIC_KEY_PATH", "",),
        "SSO_TOKEN_MAX_AGE_SECONDS": _int("SSO_TOKEN_MAX_AGE_SECONDS", 60,),
        "SSO_CLOCK_SKEW_SECONDS": _int("SSO_CLOCK_SKEW_SECONDS", 10,),
        "SESSION_JWT_SECRET": _value("SESSION_JWT_SECRET", "",),
        "SESSION_JWT_ISSUER": _value("SESSION_JWT_ISSUER", "inventarios-uno-a-uno",),
        "SESSION_JWT_AUDIENCE": _value("SESSION_JWT_AUDIENCE", "inventarios-session",),
        "SESSION_JWT_COOKIE_NAME": _value("SESSION_JWT_COOKIE_NAME", "inventario_session",),
        "SESSION_IDLE_TIMEOUT_SECONDS": _int("SESSION_IDLE_TIMEOUT_SECONDS", 1200,),
        "SESSION_COOKIE_SECURE": _bool("SESSION_COOKIE_SECURE", app_env == "production",),
        "INTRANET_URL": _value("INTRANET_URL", "",),
        "GOOGLE_MASTER_SPREADSHEET_ID": _value("GOOGLE_MASTER_SPREADSHEET_ID", "",),
        "GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID": _value("GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID", "",),
        "APP_TIMEZONE": _value("APP_TIMEZONE", "America/Bogota",),
        "GOOGLE_CREDENTIALS_PATH": _path("GOOGLE_CREDENTIALS_PATH", "credentials/credentials.json",),
        "GOOGLE_TOKEN_PATH": _path("GOOGLE_TOKEN_PATH", "credentials/token.json",),
        "GOOGLE_FORMS_COMPAT_SCRIPT_ID": _value("GOOGLE_FORMS_COMPAT_SCRIPT_ID", "",),
        "GOOGLE_HTTP_TIMEOUT": _int("GOOGLE_HTTP_TIMEOUT", 60,),
        "INVENTORY_LOCK_PATH": _path("INVENTORY_LOCK_PATH", ".runtime/inventory.lock",),
        "PREFERRED_URL_SCHEME": (
            "https"
            if app_env == "production"
            else "http"
        ),

        "DEBUG": (
            app_env != "production"
            and _bool("FLASK_DEBUG", False)
        ),

        "MAX_CONTENT_LENGTH": 8 * 1024 * 1024,
    }
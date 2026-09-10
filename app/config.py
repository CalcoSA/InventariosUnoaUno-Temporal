import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def settings():
    load_dotenv(ROOT / '.env')
    def path(name, default):
        return str((ROOT / os.getenv(name, default)).resolve())
    return {
        'APP_ENV': os.getenv('APP_ENV', 'development').strip().lower(),
        'AUTH_ENABLED': os.getenv('AUTH_ENABLED', 'false'),
        'SSO_ISSUER': os.getenv('SSO_ISSUER', 'calco-intranet'),
        'SSO_AUDIENCE': os.getenv('SSO_AUDIENCE', 'inventarios-uno-a-uno'),
        'SSO_PUBLIC_KEY_PATH': os.getenv('SSO_PUBLIC_KEY_PATH', ''),
        'SSO_TOKEN_MAX_AGE_SECONDS': os.getenv('SSO_TOKEN_MAX_AGE_SECONDS', '60'),
        'SSO_CLOCK_SKEW_SECONDS': os.getenv('SSO_CLOCK_SKEW_SECONDS', '10'),
        'SESSION_JWT_SECRET': os.getenv('SESSION_JWT_SECRET', ''),
        'SESSION_JWT_ISSUER': os.getenv('SESSION_JWT_ISSUER', 'inventarios-uno-a-uno'),
        'SESSION_JWT_AUDIENCE': os.getenv('SESSION_JWT_AUDIENCE', 'inventarios-session'),
        'SESSION_JWT_COOKIE_NAME': os.getenv('SESSION_JWT_COOKIE_NAME', 'inventario_session'),
        'SESSION_IDLE_TIMEOUT_SECONDS': os.getenv('SESSION_IDLE_TIMEOUT_SECONDS', '1200'),
        'SESSION_COOKIE_SECURE': os.getenv('SESSION_COOKIE_SECURE', 'false'),
        'INTRANET_URL': os.getenv('INTRANET_URL', ''),
        'GOOGLE_MASTER_SPREADSHEET_ID': os.getenv('GOOGLE_MASTER_SPREADSHEET_ID', ''),
        'GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID': os.getenv('GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID', ''),
        'APP_TIMEZONE': os.getenv('APP_TIMEZONE', 'America/Bogota'),
        'GOOGLE_CREDENTIALS_PATH': path('GOOGLE_CREDENTIALS_PATH', 'credentials/credentials.json'),
        'GOOGLE_TOKEN_PATH': path('GOOGLE_TOKEN_PATH', 'credentials/token.json'),
        'GOOGLE_FORMS_COMPAT_SCRIPT_ID': os.getenv('GOOGLE_FORMS_COMPAT_SCRIPT_ID', ''),
        'GOOGLE_HTTP_TIMEOUT': int(os.getenv('GOOGLE_HTTP_TIMEOUT', '60')),
        'INVENTORY_LOCK_PATH': path('INVENTORY_LOCK_PATH', '.runtime/inventory.lock'),
        'DEBUG': os.getenv('FLASK_ENV') != 'production' and os.getenv('FLASK_DEBUG', '').lower() == 'true',
        'MAX_CONTENT_LENGTH': 8 * 1024 * 1024,
    }

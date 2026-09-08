import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def settings():
    load_dotenv(ROOT / '.env')
    def path(name, default):
        return str((ROOT / os.getenv(name, default)).resolve())
    return {
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

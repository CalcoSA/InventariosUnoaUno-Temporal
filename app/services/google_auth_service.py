import json
import threading
import os
from pathlib import Path
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from app.errors import ConfigurationError

SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/forms.body']


class GoogleAuthService:
    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()

    def credentials(self, interactive=False):
        with self._lock:
            scopes = SCOPES + (['https://www.googleapis.com/auth/forms']
                               if self.config.get('GOOGLE_FORMS_COMPAT_SCRIPT_ID') else [])
            token = Path(self.config['GOOGLE_TOKEN_PATH'])
            credentials = Credentials.from_authorized_user_file(str(token)) if token.exists() else None
            changed = False
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                changed = True
            if not credentials or not credentials.valid or not credentials.has_scopes(scopes):
                client = Path(self.config['GOOGLE_CREDENTIALS_PATH'])
                if not client.exists():
                    raise ConfigurationError('Falta credentials/credentials.json: cliente OAuth 2.0 de tipo Aplicación de escritorio de Google Cloud.')
                if not interactive:
                    raise ConfigurationError('Primero ejecute python scripts/verify_google_access.py para autorizar Google y generar token.json.')
                if 'installed' not in json.loads(client.read_text(encoding='utf-8')):
                    raise ConfigurationError('credentials.json debe ser un cliente OAuth de Aplicación de escritorio, no una Service Account.')
                credentials = InstalledAppFlow.from_client_secrets_file(str(client), scopes).run_local_server(port=0, access_type='offline', prompt='consent')
                changed = True
            if changed:
                token.parent.mkdir(parents=True, exist_ok=True)
                temporary = token.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp.json')
                temporary.write_text(credentials.to_json(), encoding='utf-8')
                temporary.chmod(0o600)
                temporary.replace(token)
            return credentials

    def api(self, name, version, timeout=None):
        # Cada llamada obtiene un transporte propio: httplib2 no es thread-safe.
        http = AuthorizedHttp(self.credentials(), http=httplib2.Http(timeout=timeout or self.config['GOOGLE_HTTP_TIMEOUT']))
        return build(name, version, http=http, cache_discovery=False)

from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
import sys
from unittest.mock import Mock
import pytest
from app.errors import ConfigurationError
from app.services.google_auth_service import GoogleAuthService, SCOPES


def test_scope_upgrade_requires_reauthorization(tmp_path):
    token = tmp_path/'token.json'
    token.write_text(json.dumps({'token': 'mock-token', 'refresh_token': 'mock-refresh', 'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': 'mock', 'client_secret': 'mock', 'scopes': SCOPES,
        'expiry': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace('+00:00','Z')}))
    client = tmp_path/'client.json'
    client.write_text('{"installed":{}}')
    auth = GoogleAuthService({'GOOGLE_TOKEN_PATH': str(token), 'GOOGLE_CREDENTIALS_PATH': str(client), 'GOOGLE_FORMS_COMPAT_SCRIPT_ID': 'configured'})
    with pytest.raises(ConfigurationError, match='autorizar Google'):
        auth.credentials(interactive=False)


def test_os_lock_blocks_a_second_process(system):
    code = 'from filelock import FileLock, Timeout\nimport sys\ntry:\n with FileLock(sys.argv[1], timeout=0):\n  sys.exit(2)\nexcept Timeout:\n sys.exit(0)'
    with system.lock.acquire():
        result = subprocess.run([sys.executable, '-c', code, system.lock.path], timeout=10)
    assert result.returncode == 0
    # Tras liberar, otro proceso sí puede adquirirlo.
    assert subprocess.run([sys.executable, '-c', code, system.lock.path], timeout=10).returncode == 2

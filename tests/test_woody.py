import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from cryptography.hazmat.primitives import serialization

from test_sso import auth_config, private_key, clock, app, client  # Shared isolated auth fixtures.


def php_command():
    binary = os.environ.get('PHP_TEST_BINARY') or shutil.which('php')
    if not binary:
        pytest.skip('PHP CLI opcional para comprobar el snippet real con OpenSSL')
    command = [binary]
    if os.name == 'nt':
        command += ['-n', '-d', 'extension_dir=' + str(Path(binary).resolve().parent / 'ext'), '-d', 'extension=openssl']
    return command


@pytest.fixture
def woody(private_key, clock):
    def run(**changes):
        data = {'now': clock.value, 'private_key': private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode(), **changes}
        # Keys and JWT results exist only in pipe memory, never stdout of the test runner.
        result = subprocess.run(php_command() + ['tests/woody_harness.php', 'wordpress/inventarios-sso.php'],
            input=json.dumps(data), capture_output=True, text=True, encoding='utf-8', timeout=15)
        if result.returncode or result.stderr:
            pytest.fail('PHP snippet execution failed; output omitted to avoid exposing JWT data')
        return json.loads(result.stdout)
    return run


def test_php_signed_jwt_is_accepted_by_flask(woody, client):
    result = woody(subject='wp.usuario<&"')
    match = re.search(r'name="token" value="([^"]+)"', result['body'])
    assert match is not None
    token = html.unescape(match[1])
    response = client.post('/auth/sso', data={'token': token})
    assert response.status_code == 303
    assert client.post('/auth/sso', data={'token': token}).status_code == 401
    assert 'method="post"' in result['body']
    assert '/auth/sso?' not in result['body']
    assert 'Cache-Control: no-store, private, max-age=0' in result['headers']
    assert any(h.startswith('Content-Security-Policy:') for h in result['headers'])


def test_woody_button_opens_one_new_tab(woody):
    result = woody(scenario='render')
    assert 'INVENTARIOS PDV' in result['body']
    assert 'target="_blank"' in result['body']
    assert 'name="token"' not in result['body']
    assert 'name="_wpnonce"' in result['body']
    assert woody(scenario='render', logged_in=False)['body'] == ''


@pytest.mark.parametrize('changes,code', [({'logged_in': False}, 401), ({'missing_key': True}, 503),
    ({'nonce_valid': False}, 403), ({'method': 'GET'}, 401), ({'subject': ''}, 503),
    ({'private_key': 'invalid key'}, 503)])
def test_woody_fails_closed(woody, changes, code):
    result = woody(**changes)
    assert result['body'] == 'ACCESS DENIED ' + str(code)
    assert 'name="token"' not in result['body']

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import shutil
import subprocess
import uuid
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec

from app import create_app
from app.services.session_auth_service import ReplayCache, SessionAuthService

HEADERS = {'X-Requested-With': 'InventariosPDV', 'Origin': 'http://localhost'}


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        value = 1800000000

        def advance(self, seconds):
            self.value += seconds

    clock = Clock()

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(clock.value, tz=tz or timezone.utc)

    monkeypatch.setattr(jwt.api_jwt, 'datetime', FrozenDateTime)
    monkeypatch.setattr(SessionAuthService, 'now', staticmethod(lambda: clock.value))
    return clock


@pytest.fixture(scope='module')
def private_key():
    # Ephemeral test key in RAM; never saved or used by application configuration.
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def auth_config(tmp_path, private_key):
    public = tmp_path / 'public.pem'
    public.write_bytes(private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return {'TESTING': True, 'APP_ENV': 'testing', 'DEBUG': False, 'AUTH_ENABLED': True,
            'SSO_PUBLIC_KEY_PATH': str(public), 'SESSION_COOKIE_SECURE': False,
            'SESSION_JWT_SECRET': 'test-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'SESSION_IDLE_TIMEOUT_SECONDS': 1200}


@pytest.fixture
def app(auth_config, clock, system):
    return create_app(auth_config, {'inventory': system.inventory})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def token(private_key, clock):
    def make(changes=None, omit=(), key=None, algorithm='RS256', headers=None):
        claims = {'iss': 'calco-intranet', 'aud': 'inventarios-uno-a-uno', 'sub': 'wp.usuario',
                  'iat': clock.value, 'nbf': clock.value, 'exp': clock.value + 60, 'jti': uuid.uuid4().hex}
        claims.update(changes or {})
        for field in omit:
            claims.pop(field)
        return jwt.encode(claims, key if key is not None else private_key, algorithm=algorithm, headers=headers)
    return make


def login(client, token):
    response = client.post('/auth/sso', data={'token': token()})
    assert response.status_code == 303
    return response


def claims(app, client):
    return app.extensions['session_auth'].read_session(client.get_cookie(app.config['SESSION_JWT_COOKIE_NAME']).value)


def test_valid_sso_cookie_and_protected_inventory(app, client, token, payload, clock):
    sso = token()
    response = client.post('/auth/sso', data={'token': sso})
    assert response.status_code == 303 and response.location == '/'
    cookie = response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie and 'Path=/' in cookie
    assert 'Max-Age=1200' in cookie and 'Domain=' not in cookie
    assert sso not in cookie and sso not in response.text and sso not in response.location
    session = claims(app, client)
    assert session['sub'] == 'wp.usuario'
    assert session['exp'] == clock.value + 1200
    assert jwt.get_unverified_header(client.get_cookie('inventario_session').value)['alg'] == 'HS256'
    assert client.get('/').status_code == 200
    assert client.get('/api/puntos-venta').json == ['PDV ÁRBOL']
    assert client.post('/api/inventarios', json=payload, headers=HEADERS).json['correcto']


@pytest.mark.parametrize('changes', [
    {'iss': 'wrong'}, {'aud': 'wrong'}, {'aud': ['inventarios-uno-a-uno']},
    {'sub': ''}, {'sub': '   '}, {'sub': 1}, {'jti': ''}, {'jti': 7},
    {'iat': 1800000011}, {'nbf': 1800000011},
    {'iat': 1799999800, 'nbf': 1799999800, 'exp': 1799999860},
    {'exp': 1800000061}, {'iat': '1800000000'}, {'nbf': True}, {'exp': 1800000060.5},
    {'nbf': 1799999999}, {'exp': 1800000000},
])
def test_invalid_sso_claims(client, token, changes):
    response = client.post('/auth/sso', data={'token': token(changes)})
    assert response.status_code == 401
    assert not client.get_cookie('inventario_session')


@pytest.mark.parametrize('field', ['iss', 'aud', 'sub', 'iat', 'nbf', 'exp', 'jti'])
def test_missing_sso_claim(client, token, field):
    assert client.post('/auth/sso', data={'token': token(omit=[field])}).status_code == 401


def test_invalid_signature(client, token):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert client.post('/auth/sso', data={'token': token(key=other_key)}).status_code == 401


@pytest.mark.parametrize('algorithm,key', [('HS256', 'test-only-other-secret-0123456789abcdef'), ('none', '')])
def test_wrong_sso_algorithm(client, token, algorithm, key):
    assert client.post('/auth/sso', data={'token': token(key=key, algorithm=algorithm)}).status_code == 401


@pytest.mark.parametrize('headers', [{'typ': 'OTHER'}, {'crit': ['unknown']}])
def test_invalid_sso_header(client, token, headers):
    assert client.post('/auth/sso', data={'token': token(headers=headers)}).status_code == 401


def test_replay_single_use_across_clients(app, token):
    encoded = token()
    assert app.test_client().post('/auth/sso', data={'token': encoded}).status_code == 303
    assert app.test_client().post('/auth/sso', data={'token': encoded}).status_code == 401


def test_replay_atomic_and_ttl():
    cache = ReplayCache()
    def consume(_):
        try:
            cache.consume('same-jti', 150, 100)
            return True
        except jwt.InvalidTokenError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(consume, range(32))) == 1
    with pytest.raises(jwt.InvalidTokenError):
        cache.consume('same-jti', 150, 189)
    cache.consume('same-jti', 250, 190)


def test_clock_skew_at_most_ten_seconds(client, token, clock):
    encoded = token()
    clock.advance(69)
    assert client.post('/auth/sso', data={'token': encoded}).status_code == 303
    encoded = token()
    clock.advance(70)
    assert client.post('/auth/sso', data={'token': encoded}).status_code == 401


def test_sso_never_accepts_query_or_json_identity(client, token):
    encoded = token()
    assert client.get('/auth/sso', query_string={'token': encoded}).status_code in {401, 405}
    assert client.post('/auth/sso', query_string={'token': encoded}).status_code == 401
    assert client.post('/auth/sso?usuario=ZmFrZQ==', data={'token': encoded}).status_code == 401
    assert client.post('/auth/sso', json={'token': encoded}).status_code == 401
    assert client.get('/?usuario=ZmFrZQ==').status_code == 401


@pytest.mark.parametrize('path,method', [('/', 'get'), ('/api/puntos-venta', 'get'),
    ('/api/categorias', 'get'), ('/api/productos', 'get'), ('/api/inventarios', 'post'),
    ('/auth/activity', 'post'), ('/auth/logout', 'post'), ('/auth/status', 'post'),
    ('/static/js/inventory.js', 'get'), ('/unknown', 'get')])
def test_routes_require_session(client, path, method):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    if path.startswith(('/api/', '/auth/')):
        assert response.json == {'correcto': False, 'mensaje': 'Sesión expirada. Ingrese nuevamente desde la intranet.'}
    else:
        assert 'Acceso requerido.' in response.text


def test_health_and_access_screen_are_public(app, client):
    assert client.get('/healthz').status_code == 200
    assert client.get('/healthz').json == {'status': 'ok'}
    expired = client.get('/auth/expired')
    assert expired.status_code == 401 and 'Sesión cerrada por inactividad.' in expired.text
    assert 'href=' not in expired.text
    app.config['INTRANET_URL'] = 'https://intranet.example.test/'
    assert 'href="https://intranet.example.test/"' in client.get('/').text


def test_sliding_activity_and_exact_idle_expiration(app, client, token, clock):
    login(client, token)
    sid = claims(app, client)['sid']
    for elapsed in [600, 900, 1140]:
        clock.advance(elapsed)
        response = client.post('/auth/activity', headers=HEADERS)
        assert response.status_code == 204
        assert claims(app, client)['sid'] == sid
        assert claims(app, client)['exp'] == clock.value + 1200
    clock.advance(1199)
    assert client.get('/api/puntos-venta').status_code == 200
    clock.advance(1)
    assert client.get('/api/puntos-venta').status_code == 401
    response = client.post('/auth/activity', headers=HEADERS)
    assert response.status_code == 401 and 'Set-Cookie' not in response.headers


def test_delayed_heartbeat_uses_last_event_time(app, client, token, clock):
    login(client, token)
    clock.advance(100)
    response = client.post('/auth/activity', json={'idle_seconds': 30}, headers=HEADERS)
    assert response.status_code == 204
    assert claims(app, client)['exp'] == clock.value - 30 + 1200
    clock.advance(1170)
    assert client.post('/auth/activity', headers=HEADERS).status_code == 401


def test_status_and_background_reads_do_not_renew(app, client, token, clock):
    login(client, token)
    original = claims(app, client)['exp']
    clock.advance(1199)
    for path, method in [('/auth/status', 'post'), ('/healthz', 'get'), ('/api/puntos-venta', 'get'), ('/', 'get')]:
        response = getattr(client, method)(path, headers=HEADERS)
        assert response.status_code in {200, 204}
        assert 'Set-Cookie' not in response.headers
        assert claims(app, client)['exp'] == original
    clock.advance(1)
    assert client.post('/auth/status', headers=HEADERS).status_code == 401


@pytest.mark.parametrize('idle', [-1, 1200, '30', True, None, float('inf')])
def test_invalid_activity(client, token, idle):
    login(client, token)
    assert client.post('/auth/activity', json={'idle_seconds': idle}, headers=HEADERS).status_code == 400


def test_logout_deletes_cookie(client, token):
    login(client, token)
    response = client.post('/auth/logout', headers=HEADERS)
    assert response.status_code == 204 and 'Max-Age=0' in response.headers['Set-Cookie']
    assert client.get_cookie('inventario_session') is None
    assert client.get('/').status_code == 401


def test_expired_tab_never_deletes_new_shared_cookie(app, client, token, clock):
    login(client, token)
    old = client.get_cookie('inventario_session').value
    clock.advance(600)
    client.post('/auth/activity', headers=HEADERS)
    active_cookie = client.get_cookie('inventario_session').value
    clock.advance(600)
    stale = app.test_client()
    stale.set_cookie('inventario_session', old)
    response = stale.post('/auth/status', headers=HEADERS)
    assert response.status_code == 401 and 'Set-Cookie' not in response.headers
    assert client.get('/').status_code == 200
    assert client.get_cookie('inventario_session').value == active_cookie
    assert 'Set-Cookie' not in client.get('/auth/expired').headers


@pytest.mark.parametrize('headers', [{}, {'X-Requested-With': 'InventariosPDV', 'Origin': 'https://evil.test'},
    {'X-Requested-With': 'InventariosPDV', 'Origin': 'null'},
    {'X-Requested-With': 'InventariosPDV', 'Sec-Fetch-Site': 'cross-site'}])
def test_csrf_for_mutations(client, token, headers):
    login(client, token)
    assert client.post('/auth/activity', headers=headers).status_code == 403
    assert client.post('/auth/logout', headers=headers).status_code == 403
    assert client.post('/api/inventarios', json={}, headers=headers).status_code == 403


def test_session_signature_and_algorithm(client, token, app):
    login(client, token)
    original = claims(app, client)
    for encoded in [jwt.encode(original, 'incorrect-secret-for-tests-0123456789', algorithm='HS256'),
                    jwt.encode(original, '', algorithm='none')]:
        client.set_cookie('inventario_session', encoded)
        assert client.get('/api/puntos-venta').status_code == 401


@pytest.mark.parametrize('changes', [{'iss': 'calco-intranet'}, {'aud': 'inventarios-uno-a-uno'},
    {'sub': ''}, {'sid': ''}, {'exp': 1800009999}, {'act': 1800000100}])
def test_session_claims_are_validated(client, token, app, changes):
    login(client, token)
    invalid = {**claims(app, client), **changes}
    encoded = jwt.encode(invalid, app.config['SESSION_JWT_SECRET'], algorithm='HS256')
    client.set_cookie('inventario_session', encoded)
    assert client.post('/auth/activity', headers=HEADERS).status_code == 401


def test_internal_jwt_is_not_exposed_to_page(client, token):
    login(client, token)
    cookie = client.get_cookie('inventario_session').value
    page = client.get('/')
    assert 'js/auth.js' in page.text
    assert cookie not in page.text
    assert cookie not in str(dict(page.headers))
    assert page.headers['Cache-Control'] == 'no-store'
    assert page.headers['Referrer-Policy'] == 'no-referrer'


def test_local_development_remains_available_without_identity():
    app = create_app({'APP_ENV': 'development', 'AUTH_ENABLED': False}, {})
    client = app.test_client()
    page = client.get('/?usuario=ignored')
    assert page.status_code == 200 and 'js/auth.js' not in page.text
    assert 'Set-Cookie' not in page.headers
    assert client.post('/auth/sso', data={'token': 'fake'}).status_code == 404


def test_production_secure_cookie(auth_config, clock, token):
    app = create_app({**auth_config, 'APP_ENV': 'production', 'SESSION_COOKIE_SECURE': True}, {})
    client = app.test_client()
    response = client.post('/auth/sso', data={'token': token()}, base_url='https://localhost')
    assert response.status_code == 303 and 'Secure' in response.headers['Set-Cookie']


@pytest.mark.parametrize('changes', [
    {'AUTH_ENABLED': False}, {'SESSION_JWT_SECRET': ''}, {'SESSION_JWT_SECRET': 'short'},
    {'SESSION_JWT_SECRET': '0123456789abcdef0123456789abcdef'},
    {'SSO_PUBLIC_KEY_PATH': ''}, {'SSO_PUBLIC_KEY_PATH': '/does/not/exist.pem'},
    {'SSO_CLOCK_SKEW_SECONDS': 11}, {'SSO_CLOCK_SKEW_SECONDS': -1},
    {'SSO_TOKEN_MAX_AGE_SECONDS': 0}, {'SSO_TOKEN_MAX_AGE_SECONDS': 'no'},
    {'SESSION_IDLE_TIMEOUT_SECONDS': 0}, {'SESSION_IDLE_TIMEOUT_SECONDS': 1200.5},
    {'SESSION_COOKIE_SECURE': False}, {'DEBUG': True}, {'SSO_ISSUER': ''}, {'SSO_AUDIENCE': ''},
    {'SESSION_JWT_ISSUER': ''}, {'SESSION_JWT_AUDIENCE': ''},
    {'SESSION_JWT_COOKIE_NAME': 'bad;cookie'}, {'AUTH_ENABLED': 'yes'}, {'APP_ENV': 'prod'},
    {'INTRANET_URL': 'javascript:alert(1)'}, {'INTRANET_URL': 'http://intranet.test'},
])
def test_production_rejects_bad_config(auth_config, changes):
    with pytest.raises(ValueError):
        create_app({**auth_config, 'APP_ENV': 'production', 'SESSION_COOKIE_SECURE': True, **changes}, {})


def test_rejects_private_or_non_rsa_key(auth_config, tmp_path, private_key):
    # Private-key rejection tested without writing a private PEM onto disk.
    from unittest.mock import patch
    private = private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    for material in [private, b'not a public key', ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)]:
        with patch('app.services.session_auth_service.Path.read_bytes', return_value=material):
            with pytest.raises(ValueError):
                create_app(auth_config, {})


def test_proxy_trusts_one_local_hop_only(auth_config):
    from flask import request
    app = create_app({**auth_config, 'APP_ENV': 'production', 'SESSION_COOKIE_SECURE': True}, {})
    # Replace public health handler only in this test to inspect WSGI environment.
    app.view_functions['healthz'] = lambda: {'remote': request.remote_addr, 'scheme': request.scheme, 'host': request.host}
    headers = {'X-Forwarded-For': 'untrusted-first, 203.0.113.5', 'X-Forwarded-Proto': 'https',
               'X-Forwarded-Host': 'evil.test', 'Host': 'inventory.test'}
    client = app.test_client()
    trusted = client.get('/healthz', headers=headers, environ_base={'REMOTE_ADDR': '127.0.0.1'}).json
    assert trusted == {'remote': '203.0.113.5', 'scheme': 'https', 'host': 'inventory.test'}
    untrusted = client.get('/healthz', headers=headers, environ_base={'REMOTE_ADDR': '198.51.100.2'}).json
    assert untrusted == {'remote': '198.51.100.2', 'scheme': 'http', 'host': 'inventory.test'}


def test_no_tokens_in_logs(app, client, token, caplog):
    encoded = token()
    with caplog.at_level('INFO'):
        response = client.post('/auth/sso', data={'token': encoded})
        client.post('/auth/sso', data={'token': encoded})
        session_token = client.get_cookie('inventario_session').value
        client.post('/auth/logout', headers=HEADERS)
    assert encoded not in caplog.text and session_token not in caplog.text
    assert app.config['SESSION_JWT_SECRET'] not in caplog.text


def test_frontend_auth_scenarios():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js requerido para las pruebas de pestañas y reloj de JavaScript')
    result = subprocess.run([node, 'tests/auth_frontend.cjs'], capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_wsgi_import_without_network():
    import wsgi
    assert callable(wsgi.app)
    assert wsgi.app.test_client().get('/healthz').json == {'status': 'ok'}

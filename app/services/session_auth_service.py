"""WordPress identity and internal sessions. Independent of Google OAuth."""
import hashlib
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey


def validate_auth_config(config):
    if config['APP_ENV'] not in {'development', 'production', 'testing'}:
        raise ValueError('APP_ENV debe ser development, testing o production.')
    for name in ('AUTH_ENABLED', 'SESSION_COOKIE_SECURE'):
        value = config[name]
        if isinstance(value, str) and value.lower() in {'true', 'false'}:
            value = value.lower() == 'true'
        if type(value) is not bool:
            raise ValueError(f'{name} debe ser true o false.')
        config[name] = value
    for name, minimum, maximum in (
        ('SSO_TOKEN_MAX_AGE_SECONDS', 1, 300),
        ('SSO_CLOCK_SKEW_SECONDS', 0, 10),
        ('SESSION_IDLE_TIMEOUT_SECONDS', 60, 86400),
    ):
        value = config[name]
        if type(value) is not int and not (isinstance(value, str) and value.isascii() and value.isdigit()):
            raise ValueError(f'{name} debe ser un entero.')
        config[name] = int(value)
        if not minimum <= config[name] <= maximum:
            raise ValueError(f'{name} debe estar entre {minimum} y {maximum}.')
    production = config['APP_ENV'] == 'production'
    if production and (not config['AUTH_ENABLED'] or not config['SESSION_COOKIE_SECURE'] or config['DEBUG']):
        raise ValueError('Producción exige AUTH_ENABLED=true, SESSION_COOKIE_SECURE=true y DEBUG=false.')
    if config['INTRANET_URL']:
        url = urlsplit(config['INTRANET_URL'])
        if url.scheme not in {'http', 'https'} or not url.netloc or url.username or url.password:
            raise ValueError('INTRANET_URL debe ser una URL HTTP(S) válida.')
        if production and url.scheme != 'https':
            raise ValueError('INTRANET_URL debe utilizar HTTPS en producción.')
    for name in ('SSO_ISSUER', 'SSO_AUDIENCE', 'SESSION_JWT_ISSUER', 'SESSION_JWT_AUDIENCE'):
        if not isinstance(config[name], str) or not config[name].strip():
            raise ValueError(f'{name} no puede estar vacío.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', config['SESSION_JWT_COOKIE_NAME']):
        raise ValueError('SESSION_JWT_COOKIE_NAME no es válido.')
    if config['SESSION_JWT_COOKIE_NAME'].startswith(('__Host-', '__Secure-')) and not config['SESSION_COOKIE_SECURE']:
        raise ValueError('El prefijo de cookie requiere SESSION_COOKIE_SECURE=true.')
    if not config['AUTH_ENABLED']:
        return None
    secret = config['SESSION_JWT_SECRET']
    if not isinstance(secret, str) or len(secret.encode('utf-8')) < 32 or len(set(secret)) < 8:
        raise ValueError('SESSION_JWT_SECRET requiere al menos 32 bytes aleatorios independientes.')
    if '-----BEGIN ' in secret or (re.fullmatch(r'[0-9a-fA-F]+', secret) and len(secret) < 64):
        raise ValueError('SESSION_JWT_SECRET debe ser independiente de RSA y contener al menos 256 bits (64 caracteres hex).')
    key_path = config['SSO_PUBLIC_KEY_PATH']
    if not key_path:
        raise ValueError('Configure SSO_PUBLIC_KEY_PATH con una clave pública RSA.')
    try:
        # load_pem_public_key deliberately rejects private keys and non-RSA keys.
        public_key = serialization.load_pem_public_key(Path(key_path).read_bytes())
    except (OSError, ValueError, TypeError):
        raise ValueError('SSO_PUBLIC_KEY_PATH debe existir y contener una clave pública RSA PEM.') from None
    if not isinstance(public_key, RSAPublicKey) or public_key.key_size < 2048:
        raise ValueError('SSO_PUBLIC_KEY_PATH requiere una clave pública RSA de al menos 2048 bits.')
    return public_key


class ReplayCache:
    """Atomic TTL consumption; one process, shared by all Gunicorn threads."""
    def __init__(self):
        self._used = {}
        self._lock = threading.Lock()

    def consume(self, jti, expires_at, now):
        with self._lock:
            self._used = {key: expiry for key, expiry in self._used.items() if expiry > now}
            if jti in self._used:
                raise jwt.InvalidTokenError('replay rechazado')
            self._used[jti] = max(now + 90, expires_at)


class SessionAuthService:
    def __init__(self, config, public_key):
        self.config = config
        self.public_key = public_key
        self.replay = ReplayCache()

    @staticmethod
    def now():
        return int(time.time())

    @staticmethod
    def _decode(token, key, algorithm, issuer, audience, required, leeway=0):
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise jwt.InvalidTokenError('token inválido')
        header = jwt.get_unverified_header(token)
        if header.get('alg') != algorithm or header.get('typ') != 'JWT' or header.get('crit'):
            raise jwt.InvalidTokenError('header inválido')
        claims = jwt.decode(token, key, algorithms=[algorithm], issuer=issuer, audience=audience,
                            leeway=leeway, options={'require': required, 'strict_aud': True})
        if not isinstance(claims['sub'], str) or not claims['sub'].strip() or len(claims['sub']) > 256:
            raise jwt.InvalidTokenError('subject inválido')
        for field in ('iat', 'nbf', 'exp', 'act'):
            if field in claims and (type(claims[field]) is not int or claims[field] < 0):
                raise jwt.InvalidTokenError('fecha inválida')
        return claims

    def consume_sso(self, token):
        c = self.config
        claims = self._decode(token, self.public_key, 'RS256', c['SSO_ISSUER'], c['SSO_AUDIENCE'],
                              ['iss', 'aud', 'sub', 'iat', 'nbf', 'exp', 'jti'], c['SSO_CLOCK_SKEW_SECONDS'])
        if not claims['iat'] <= claims['nbf'] < claims['exp']:
            raise jwt.InvalidTokenError('fechas inconsistentes')
        if not 0 < claims['exp'] - claims['iat'] <= c['SSO_TOKEN_MAX_AGE_SECONDS']:
            raise jwt.InvalidTokenError('vida SSO excedida')
        if self.now() - claims['iat'] > c['SSO_TOKEN_MAX_AGE_SECONDS'] + c['SSO_CLOCK_SKEW_SECONDS']:
            raise jwt.InvalidTokenError('token antiguo')
        if not isinstance(claims['jti'], str) or not claims['jti'].strip() or len(claims['jti']) > 256:
            raise jwt.InvalidTokenError('jti inválido')
        self.replay.consume(claims['jti'], claims['exp'] + c['SSO_CLOCK_SKEW_SECONDS'], self.now())
        return self.new_session(claims['sub'])

    def new_session(self, subject):
        now = self.now()
        return {'iss': self.config['SESSION_JWT_ISSUER'], 'aud': self.config['SESSION_JWT_AUDIENCE'],
                'sub': subject, 'iat': now, 'act': now,
                'exp': now + self.config['SESSION_IDLE_TIMEOUT_SECONDS'], 'sid': str(uuid.uuid4())}

    def read_session(self, token):
        c = self.config
        claims = self._decode(token, c['SESSION_JWT_SECRET'], 'HS256', c['SESSION_JWT_ISSUER'],
                              c['SESSION_JWT_AUDIENCE'], ['iss', 'aud', 'sub', 'iat', 'exp', 'sid', 'act'])
        try:
            if str(uuid.UUID(claims['sid'])) != claims['sid']:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise jwt.InvalidTokenError('sid inválido') from None
        if not claims['act'] <= claims['iat'] < claims['exp'] or claims['exp'] - claims['act'] != c['SESSION_IDLE_TIMEOUT_SECONDS']:
            raise jwt.InvalidTokenError('sesión inconsistente')
        return claims

    def renew(self, claims, idle_seconds=0):
        now = self.now()
        if claims['exp'] <= now:
            raise jwt.ExpiredSignatureError('sesión expirada')
        # The heartbeat reports elapsed inactivity, never an absolute client clock.
        activity = max(claims['act'], now - idle_seconds)
        if activity + self.config['SESSION_IDLE_TIMEOUT_SECONDS'] <= now:
            raise jwt.ExpiredSignatureError('actividad expirada')
        return {**claims, 'iat': now, 'act': activity,
                'exp': activity + self.config['SESSION_IDLE_TIMEOUT_SECONDS']}

    def set_cookie(self, response, claims):
        c = self.config
        token = jwt.encode(claims, c['SESSION_JWT_SECRET'], algorithm='HS256', headers={'typ': 'JWT'})
        response.set_cookie(c['SESSION_JWT_COOKIE_NAME'], token, httponly=True,
                            secure=c['SESSION_COOKIE_SECURE'], samesite='Lax', path='/',
                            max_age=max(0, claims['exp'] - self.now()))

    def delete_cookie(self, response):
        response.delete_cookie(self.config['SESSION_JWT_COOKIE_NAME'], path='/', httponly=True,
                               secure=self.config['SESSION_COOKIE_SECURE'], samesite='Lax')

    @staticmethod
    def context(claims):
        # Correlation of tabs, never a credential or the session JWT.
        return hashlib.sha256(claims['sid'].encode()).hexdigest()[:24]

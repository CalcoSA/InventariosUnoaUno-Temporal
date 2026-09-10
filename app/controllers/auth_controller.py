import math
from urllib.parse import urlsplit

import jwt
from flask import Blueprint, current_app, g, jsonify, make_response, redirect, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app.services.session_auth_service import SessionAuthService, validate_auth_config

auth = Blueprint('auth', __name__, url_prefix='/auth')
EXPIRED = 'Sesión expirada. Ingrese nuevamente desde la intranet.'


class LocalProxyFix:
    """Exactly one trusted hop, and only when the actual peer is loopback."""
    def __init__(self, app):
        self.app = app
        self.proxy = ProxyFix(app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)

    def __call__(self, environ, start_response):
        application = self.proxy if environ.get('REMOTE_ADDR') in {'127.0.0.1', '::1'} else self.app
        return application(environ, start_response)


def service():
    return current_app.extensions['session_auth']


def access_response(expired=False):
    return make_response(render_template('access.html', expired=expired), 401)


def unauthorized():
    if request.path.startswith(('/api/', '/auth/activity', '/auth/status', '/auth/logout')):
        return jsonify(correcto=False, mensaje=EXPIRED), 401
    return access_response()


def register_auth(app):
    public_key = validate_auth_config(app.config)
    app.extensions['session_auth'] = SessionAuthService(app.config, public_key)
    app.register_blueprint(auth)
    if app.config['APP_ENV'] == 'production':
        app.wsgi_app = LocalProxyFix(app.wsgi_app)

    @app.get('/healthz')
    def healthz():
        return jsonify(status='ok')

    @app.before_request
    def protect():
        if not app.config['AUTH_ENABLED']:
            return None
        if request.endpoint in {'auth.sso', 'auth.expired', 'healthz'}:
            return None
        try:
            g.auth_session = service().read_session(request.cookies.get(app.config['SESSION_JWT_COOKIE_NAME']))
        except jwt.InvalidTokenError:
            # Do not delete a shared cookie from a stale request in another tab.
            return unauthorized()
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('Origin')
            expected = urlsplit(request.host_url)
            actual = urlsplit(origin) if origin else None
            if (request.headers.get('X-Requested-With') != 'InventariosPDV' or
                    (actual and (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc)) or
                    request.headers.get('Sec-Fetch-Site') == 'cross-site'):
                return jsonify(correcto=False, mensaje='Origen de solicitud no permitido.'), 403

    @app.after_request
    def session_headers(response):
        if app.config['AUTH_ENABLED'] or request.path.startswith('/auth/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        claims = getattr(g, 'auth_session', None)
        if claims and response.status_code < 400:
            response.headers['X-Session-Expires-At'] = str(claims['exp'])
            response.headers['X-Session-Activity-At'] = str(claims['act'])
            response.headers['X-Server-Time'] = str(service().now())
            response.headers['X-Session-Context'] = service().context(claims)
        return response

    @app.context_processor
    def auth_template():
        claims = getattr(g, 'auth_session', None)
        return {'auth_session_context': service().context(claims) if claims else '',
                'auth_remaining_seconds': max(0, claims['exp'] - service().now()) if claims else 0}


@auth.post('/sso')
def sso():
    if not current_app.config['AUTH_ENABLED']:
        return jsonify(correcto=False, mensaje='SSO no está habilitado.'), 404
    # POST form only. In particular, never read request.values or a query token.
    if request.query_string or request.content_length is None or request.content_length > 16384:
        return access_response()
    tokens = request.form.getlist('token')
    try:
        if len(tokens) != 1:
            raise jwt.InvalidTokenError('token faltante')
        g.auth_session = service().consume_sso(tokens[0])
    except jwt.InvalidTokenError:
        current_app.logger.info('SSO rechazado: token inválido, expirado o replay.')
        return access_response()
    response = redirect('/', code=303)
    service().set_cookie(response, g.auth_session)
    current_app.logger.info('Login SSO exitoso.')
    return response


@auth.post('/activity')
def activity():
    if not getattr(g, 'auth_session', None):
        return unauthorized()
    data = request.get_json(silent=True) or {}
    idle = data.get('idle_seconds', 0) if isinstance(data, dict) else None
    if type(idle) not in {int, float} or not math.isfinite(idle) or not 0 <= idle < current_app.config['SESSION_IDLE_TIMEOUT_SECONDS']:
        return jsonify(correcto=False, mensaje='Actividad inválida.'), 400
    try:
        g.auth_session = service().renew(g.auth_session, math.ceil(idle))
    except jwt.InvalidTokenError:
        return unauthorized()
    response = make_response('', 204)
    service().set_cookie(response, g.auth_session)
    return response


@auth.post('/status')
def status():
    """Checks shared cookie at idle boundary; does not renew it or count as activity."""
    if not getattr(g, 'auth_session', None):
        return unauthorized()
    return '', 204


@auth.post('/logout')
def logout():
    if not getattr(g, 'auth_session', None):
        return unauthorized()
    response = make_response('', 204)
    service().delete_cookie(response)
    current_app.logger.info('Logout.')
    return response


@auth.get('/expired')
def expired():
    return access_response(expired=True)

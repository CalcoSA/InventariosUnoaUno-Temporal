import logging
from flask import Flask
from app.config import settings
from app.container import build_services


def create_app(config=None, services=None):
    app = Flask(__name__)
    app.config.from_mapping(settings())
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    from app.controllers.auth_controller import register_auth
    register_auth(app)
    app.extensions['services'] = services if services is not None else build_services(app.config)
    from app.controllers.web_controller import web
    from app.controllers.inventory_controller import inventory
    from app.controllers.error_controller import register_errors
    app.register_blueprint(web)
    app.register_blueprint(inventory)
    register_errors(app)

    @app.after_request
    def secure_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        if response.mimetype == 'application/json':
            response.headers['Cache-Control'] = 'no-store'
        return response

    return app

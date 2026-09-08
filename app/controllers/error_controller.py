from flask import jsonify
from werkzeug.exceptions import HTTPException
from googleapiclient.errors import HttpError
from app.errors import FunctionalError, ConfigurationError


def register_errors(app):
    @app.errorhandler(FunctionalError)
    def functional(error):
        return jsonify(correcto=False, mensaje=str(error)), 503 if isinstance(error, ConfigurationError) else 400

    @app.errorhandler(HttpError)
    def google(error):
        app.logger.exception('Error de Google API')
        message = {401: 'La autorización de Google expiró. Ejecute la verificación de acceso.',
                   403: 'Google denegó el acceso. Verifique los permisos del archivo y las APIs habilitadas.',
                   404: 'No se encontró el archivo solicitado en Google.',
                   429: 'Google está recibiendo demasiadas solicitudes. Intente nuevamente.'}.get(error.resp.status,
                   'No se pudo completar la operación con Google. Revise el registro del servidor.')
        return jsonify(correcto=False, mensaje=message), 502

    @app.errorhandler(HTTPException)
    def http(error):
        return jsonify(correcto=False, mensaje={400: 'La solicitud no es válida.', 404: 'No se encontró la página solicitada.',
                       405: 'Método no permitido.', 413: 'El inventario supera el tamaño máximo permitido.'}.get(error.code, 'No se pudo procesar la solicitud.')), error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception('Error inesperado')
        return jsonify(correcto=False, mensaje='Ocurrió un error inesperado. Revise el registro del servidor.'), 500

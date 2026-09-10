from flask import Blueprint, current_app, jsonify, request
from app.errors import FunctionalError

inventory = Blueprint('inventory', __name__, url_prefix='/api')


def service():
    return current_app.extensions['services']['inventory']


@inventory.get('/puntos-venta')
def points_of_sale():
    return jsonify(service().get_points_of_sale())


@inventory.get('/categorias')
def categories():
    return jsonify(service().get_categories(request.args.get('pdv', '')))


@inventory.get('/productos')
def products():
    return jsonify(service().get_products(request.args.get('pdv', ''), request.args.get('categoria')))


@inventory.post('/inventarios')
def save():
    if not request.is_json:
        raise FunctionalError('Debe enviar los datos del inventario en formato JSON.')
    return jsonify(service().save_inventory(request.get_json()))

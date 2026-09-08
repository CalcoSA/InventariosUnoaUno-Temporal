from unittest.mock import Mock
from app import create_app
from app.errors import FunctionalError


def test_endpoints_and_save(system, payload):
    client = create_app({'TESTING': True}, {'inventory': system.inventory}).test_client()
    assert client.get('/').status_code == 200
    assert 'CREPES &amp; WAFFLES' in client.get('/').text or 'CREPES & WAFFLES' in client.get('/').text
    assert client.get('/static/css/inventory.css').status_code == 200
    assert client.get('/static/js/inventory.js').status_code == 200
    assert client.get('/api/puntos-venta').json == ['PDV ÁRBOL']
    assert client.get('/api/categorias', query_string={'pdv': 'PDV ÁRBOL'}).json == ['BEBIDAS']
    assert len(client.get('/api/productos', query_string={'pdv': 'PDV ÁRBOL', 'categoria': 'bebidas'}).json) == 2
    assert client.post('/api/inventarios', json=payload).json['correcto'] is True
    failure = client.post('/api/inventarios', json=payload)
    assert failure.status_code == 400
    assert 'ya fue guardada' in failure.json['mensaje']
    assert failure.headers['X-Content-Type-Options'] == 'nosniff'


def test_errors_never_expose_tracebacks():
    mock = Mock()
    mock.get_points_of_sale.side_effect = RuntimeError('private stack information')
    client = create_app({'TESTING': True}, {'inventory': mock}).test_client()
    response = client.get('/api/puntos-venta')
    assert response.status_code == 500
    assert 'private stack' not in response.text
    assert client.post('/api/inventarios', data='{', content_type='application/json').status_code == 400
    assert client.post('/api/inventarios', data='abc').status_code == 400
    assert client.get('/missing').status_code == 404


def test_missing_credentials_has_actionable_message(tmp_path):
    client = create_app({'TESTING': True, 'GOOGLE_TOKEN_PATH': str(tmp_path/'token.json'),
        'GOOGLE_CREDENTIALS_PATH': str(tmp_path/'credentials.json')}).test_client()
    # El doble global bloquea api antes de leer credenciales; comprobar proveedor directamente.
    from app.services.google_auth_service import GoogleAuthService
    import pytest
    with pytest.raises(FunctionalError, match='Aplicación de escritorio'):
        GoogleAuthService({'GOOGLE_TOKEN_PATH': str(tmp_path/'token.json'), 'GOOGLE_CREDENTIALS_PATH': str(tmp_path/'credentials.json')}).credentials()

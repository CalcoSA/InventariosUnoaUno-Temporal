import pytest
from app.errors import FunctionalError
from app.models.inventory_count import InventoryCount


def test_calculation():
    assert InventoryCount('001', 2, 3, 12).conteo_fisico == 27


def test_save_12_columns_and_uuid(system, payload):
    payload['conteos'].append(dict(payload['conteos'][0], item='002', udm='unidad'))
    payload['conteos'][0]['factor'] = 9999
    assert system.inventory.save_inventory(payload) == {'correcto': True, 'mensaje': 'Inventario guardado correctamente.', 'registros': 2}
    rows = system.pdv.counts('pdv')[1:]
    assert all(len(r) == 12 for r in rows)
    assert rows[0][0] == rows[1][0]
    assert rows[0][10:] == [12, 27]
    assert rows[1][10:] == [2, 7]
    assert len(system.general.rows()) == 2


@pytest.mark.parametrize('field,value', [('cerrado', '-1'), ('abierto', 'no'), ('cerrado', 'Infinity'), ('abierto', 'NaN')])
def test_invalid_quantities(system, payload, field, value):
    payload['conteos'][0][field] = value
    with pytest.raises(FunctionalError, match='no es válida'):
        system.inventory.save_inventory(payload)
    assert 'Conteos Inventarios' not in system.sheets.books['pdv']


def test_partial_and_empty_rows_match_legacy(system, payload):
    payload['conteos'][0].update(cerrado='', abierto='2,5')
    payload['conteos'].append({'cerrado': '', 'abierto': ''})
    assert system.inventory.save_inventory(payload)['registros'] == 1
    assert system.pdv.counts('pdv')[1][8:] == [0, 2.5, 12, 2.5]


def test_display_filter_keeps_legacy_factor_index(system):
    system.sheets.books['pdv']['Uno a Uno'] = [['Categoria', 'Item', 'Producto', 'UDM', 'Factor'],
        ['A', '', '', '', 5], ['A', '001', 'Producto', 'unidad', 9]]
    assert system.inventory.get_products('PDV ÁRBOL')[0]['factor'] == 5
    assert system.pdv.factors('pdv')['001'] == 9


def test_read_points_and_categories(system):
    assert system.inventory.get_points_of_sale() == ['PDV ÁRBOL']
    assert system.inventory.get_categories('PDV ÁRBOL') == ['BEBIDAS']
    assert len(system.inventory.get_products('PDV ÁRBOL', 'bebídas')) == 2

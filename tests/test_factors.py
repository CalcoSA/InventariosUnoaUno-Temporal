import pytest
from app.utils import correct_factor, normalize_factor


@pytest.mark.parametrize('udm,value,expected', [('X 12', 1, 12), ('x6', 100, 6), ('X 2,5', 1, 2.5),
    ('unidad', 120000, 12), ('', 1200000000, 12), ('', '', 1), ('', -1, 1), ('X 0', 3, 3),
    ('caja X 12', 2, 2), ('X 10000', 1, 10000), ('', '2,5', 2.5), ('', 'texto', 1), ('', 'Infinity', 1)])
def test_correct_factor(udm, value, expected):
    assert correct_factor(udm, value) == expected


def test_historical_loop():
    assert normalize_factor(1200000000) == 12


def test_factor_requires_factor_column_like_legacy(system):
    system.sheets.books['pdv']['Uno a Uno'] = [['Item', 'Producto', 'UDM'], ['001', 'Agua', 'X 12']]
    assert system.pdv.factors('pdv') == {}

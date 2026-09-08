import pytest
from app.utils import normalize, normalize_simple, find_index, spanish_key


@pytest.mark.parametrize('value,expected', [('Categoría', 'categoria'), ('categoria', 'categoria'), ('CATEGORIA', 'categoria'),
    ('Desc. U.M.', 'desc u m'), ('desc um', 'desc um'), ('Factor_U.M.', 'factor u m'), (' Uno--a__Uno ', 'uno a uno')])
def test_normalization(value, expected):
    assert normalize(value) == expected


def test_simple_does_not_replace_punctuation():
    assert normalize_simple(' Á.B_ C--D ') == 'a.b_ c--d'
    assert normalize('Desc. U.M.') != normalize('desc um')
    assert find_index(['Desc. U.M.'], ['desc um', 'desc u m']) == 0


def test_spanish_sort():
    assert sorted(['Oso', 'Ñame', 'Nube', 'Árbol'], key=spanish_key) == ['Árbol', 'Nube', 'Ñame', 'Oso']

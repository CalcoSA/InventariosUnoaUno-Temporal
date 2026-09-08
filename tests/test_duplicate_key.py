from concurrent.futures import ThreadPoolExecutor
import pytest
from app.errors import FunctionalError
from app.utils import summary_key, duplicate_key


def test_normalized_keys():
    assert summary_key('08/09/2026', 'PDV ÁRBOL', '001') == summary_key('2026-09-08', 'pdv arbol', '001')
    assert duplicate_key('08-09-2026', 'PDV ÁRBOL', 'BEBÍDAS') == duplicate_key('2026-09-08', 'pdv arbol', 'bebidas')
    assert summary_key('', '', '') == ''


def test_rejected_duplicate(system, payload):
    system.inventory.save_inventory(payload)
    payload['fecha'] = '08/09/2026'
    payload['categoria'] = 'bebídas'
    with pytest.raises(FunctionalError, match='ya fue guardada'):
        system.inventory.save_inventory(payload)
    assert len(system.pdv.counts('pdv')) == 2


def test_simultaneous_submissions(system, payload):
    def save(_):
        try:
            return system.inventory.save_inventory(payload)['correcto']
        except FunctionalError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, range(2))) == [False, True]
    assert len(system.pdv.counts('pdv')) == 2

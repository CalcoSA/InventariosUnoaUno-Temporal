"""Carga local y conteo de REST mediante transporte simulado; nunca usa Google real."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Lock
from unittest.mock import Mock

import pytest

from app import create_app
from app.constants import COUNT_HEADERS, SUMMARY_HEADERS
from app.errors import FunctionalError
from app.repositories.general_summary_repository import GeneralSummaryRepository
from app.repositories.master_sheet_repository import MasterSheetRepository
from app.repositories.pdv_sheet_repository import PdvSheetRepository
from app.services.google_sheets_service import GoogleSheetsService
from app.services.inventory_service import InventoryService
from app.services.inventory_summary_service import InventorySummaryService
from app.utils import js_string


class CountingGoogle:
    """Ejecuta lecturas de grids simulados y cuenta cada request.execute real.

    Las escrituras solo se cuentan. Su contenido/duplicados se comprueba con
    MemorySheets en los tests funcionales; aquí medimos el presupuesto de REST.
    """

    def __init__(self, memory):
        self.memory = memory
        self.calls = []
        self.lock = Lock()
        self.auth = Mock()
        api = self.auth.api.return_value.spreadsheets.return_value
        api.get.side_effect = self.get
        api.batchUpdate.side_effect = lambda **kw: self.request('batchUpdate', kw)
        api.values.return_value.clear.side_effect = lambda **kw: self.request('clear', kw)

    def request(self, method, params, result=None):
        def execute(**kwargs):
            assert kwargs == {'num_retries': 0}
            with self.lock:
                self.calls.append((method, params['spreadsheetId'], tuple(params.get('ranges', []))))
            return result() if result else {}
        return Mock(execute=execute)

    def get(self, **params):
        def result():
            book = params['spreadsheetId']
            if 'ranges' not in params:
                return self.memory.metadata(book)
            title = params['ranges'][0][1:-1].replace("''", "'")
            rows = self.memory.books[book][title]
            return {'properties': {'timeZone': 'America/Bogota'}, 'sheets': [{'data': [{'rowData': [
                {'values': [{'effectiveValue': {
                    ('numberValue' if isinstance(value, (int, float)) else 'stringValue'): value},
                    'formattedValue': js_string(value)} for value in row]} for row in rows]}]}]}
        return self.request('get', params, result)


def measured_services(system):
    google = CountingGoogle(system.sheets)
    sheets = GoogleSheetsService(google.auth)
    master = MasterSheetRepository(sheets, 'master')
    pdv = PdvSheetRepository(sheets, master)
    general = GeneralSummaryRepository(sheets, 'general')
    summary = InventorySummaryService(master, pdv, general, system.lock, system.now)
    inventory = InventoryService(master, pdv, summary, system.lock, system.now)
    return google, inventory


@pytest.mark.parametrize('users', [10, 20, 40])
def test_concurrent_read_flows_use_four_google_requests(system, users):
    google, inventory = measured_services(system)
    app = create_app({'TESTING': True}, {'inventory': inventory})
    start = Barrier(users)

    def browse(_):
        with app.test_client() as client:
            start.wait(timeout=10)
            assert client.get('/api/puntos-venta').json == ['PDV ÁRBOL']
            assert client.get('/api/categorias', query_string={'pdv': 'PDV ÁRBOL'}).json == ['BEBIDAS']
            response = client.get('/api/productos', query_string={'pdv': 'PDV ÁRBOL', 'categoria': 'bebidas'})
            assert response.status_code == 200
            assert response.json[0]['factor'] == 12
            assert len(response.json) == 2

    with ThreadPoolExecutor(max_workers=users) as pool:
        list(pool.map(browse, range(users)))
    assert Counter(google.calls) == {
        ('get', 'master', ()): 1,
        ('get', 'master', ("'Control Formularios'",)): 1,
        ('get', 'pdv', ()): 1,
        ('get', 'pdv', ("'Uno a Uno'",)): 1,
    }


def test_catalog_ttls_and_separation_by_book(system):
    system.sheets.books['master']['Control Formularios'].append(['f2', 'PDV B', 'LISTO', 'pdv-b'])
    system.sheets.books['pdv-b'] = {'Uno a Uno': [
        ['Categoría', 'Item', 'Producto', 'Desc. U.M.', 'Factor U.M.'], ['OTRA', '001', 'Otro', 'unidad', 7]]}
    google, inventory = measured_services(system)
    clock = Mock(return_value=0)
    inventory.master._control_cache.clock = clock
    inventory._products_cache.clock = clock
    assert inventory.get_products('PDV ÁRBOL')[0]['factor'] == 12
    assert inventory.get_products('PDV B')[0]['factor'] == 7
    assert inventory.get_categories('PDV B') == ['OTRA']
    assert inventory.get_products('PDV B', 'BEBIDAS') == []
    assert len(google.calls) == 6
    clock.return_value = 44.9
    inventory.get_products('PDV ÁRBOL')
    assert len(google.calls) == 6
    clock.return_value = 45
    inventory.get_products('PDV ÁRBOL')
    assert len(google.calls) == 8  # Solo refresca Control Formularios.
    clock.return_value = 179.9
    inventory.get_products('PDV ÁRBOL')
    assert len(google.calls) == 10
    clock.return_value = 180
    inventory.get_products('PDV ÁRBOL')
    assert len(google.calls) == 12  # Ahora refresca metadatos y Uno a Uno.


def test_read_call_budget_cold_and_warm(system):
    google, inventory = measured_services(system)
    inventory.get_points_of_sale()
    assert len(google.calls) == 2
    inventory.get_categories('PDV ÁRBOL')
    assert len(google.calls) == 4
    inventory.get_products('PDV ÁRBOL', 'BEBIDAS')
    assert len(google.calls) == 4
    inventory.get_points_of_sale()
    inventory.get_categories('PDV ÁRBOL')
    assert len(google.calls) == 4


def test_save_call_budget_with_existing_sheets(system, payload):
    # Hojas existentes, grilla suficiente, un grupo nuevo, sin reintentos.
    system.sheets.books['pdv']['Conteos Inventarios'] = [COUNT_HEADERS,
        ['old', '', '2026-09-07', 'PDV ÁRBOL', 'BEBIDAS', '001', 'Agua', 'X 12', 1, 0, 12, 12]]
    system.sheets.books['pdv']['Resumen Inventario'] = [SUMMARY_HEADERS]
    google, inventory = measured_services(system)
    inventory.get_products('PDV ÁRBOL')  # Una caché caliente no evita lecturas del guardado.
    google.calls.clear()
    assert inventory.save_inventory(payload)['correcto'] is True
    assert len(google.calls) == 10
    assert Counter(google.calls)[('get', 'pdv', ("'Uno a Uno'",))] == 1
    assert Counter(method for method, *_ in google.calls) == {'get': 8, 'batchUpdate': 2}


def test_save_uses_fresh_mapping_factors_and_duplicate_counts(system, payload):
    system.inventory.get_products('PDV ÁRBOL')
    # Un catálogo visible antiguo no puede definir el factor usado para guardar.
    system.sheets.books['pdv']['Uno a Uno'][1][3:5] = ['unidad', 7]
    payload['conteos'][0]['udm'] = 'unidad'
    assert system.inventory.save_inventory(payload)['correcto']
    assert system.pdv.counts('pdv')[1][10:] == [7, 17]
    assert system.sheets.books['pdv']['Resumen Inventario'][1][7:9] == [7, 17]
    assert system.general.rows()[0][7:9] == [7, 17]
    with pytest.raises(FunctionalError, match='ya fue guardada'):
        system.inventory.save_inventory(payload)
    assert len(system.pdv.counts('pdv')) == 2
    # También se revalida Control Formularios aunque la lista pública esté cacheada.
    system.sheets.books['master']['Control Formularios'][1][2] = 'PENDIENTE'
    with pytest.raises(FunctionalError, match='No se encontró la base'):
        system.inventory.save_inventory(payload)


def test_twenty_saves_with_warm_catalog_accept_only_one(system, payload):
    system.inventory.get_products('PDV ÁRBOL')
    start = Barrier(20)

    def save(_):
        start.wait(timeout=10)
        try:
            return system.inventory.save_inventory(deepcopy(payload))['correcto']
        except FunctionalError as error:
            assert 'ya fue guardada' in str(error)
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        assert sum(pool.map(save, range(20))) == 1
    assert len(system.pdv.counts('pdv')) == 2
    assert system.pdv.counts('pdv')[1][10:] == [12, 27]
    assert system.sheets.books['pdv']['Resumen Inventario'][1][5:9] == [2, 3, 12, 27]
    assert system.general.rows()[0][5:9] == [2, 3, 12, 27]


def test_summary_still_reads_factors_when_saved_column_is_missing(system, monkeypatch):
    system.sheets.books['pdv']['Conteos Inventarios'] = [
        COUNT_HEADERS[:10], ['old', '', '2026-09-08', 'PDV ÁRBOL', 'BEBIDAS', '001', 'Agua', 'X 12', 2, 3]]
    factors = Mock(wraps=system.pdv.factors)
    monkeypatch.setattr(system.pdv, 'factors', factors)
    records = system.summary.records_from_counts('pdv', strict=True)
    assert records[0][7:9] == [12, 27]
    factors.assert_called_once_with('pdv')

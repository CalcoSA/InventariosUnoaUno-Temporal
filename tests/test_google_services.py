import json
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo
import httplib2
import pytest
from googleapiclient.errors import HttpError
from app.services.google_request import execute
from app.services.google_forms_service import GoogleFormsService
from app.services.google_sheets_service import GoogleSheetsService
from app.services.forms_compatibility_adapter import FormsCompatibilityAdapter
from app.errors import FunctionalError


def http_error(status):
    return HttpError(httplib2.Response({'status': status}), b'{"error":{"message":"Google error"}}')


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_transient_retries(status, monkeypatch):
    request = Mock()
    request.execute.side_effect = [http_error(status), {'ok': True}]
    sleep = Mock()
    monkeypatch.setattr('app.services.google_request.time.sleep', sleep)
    assert execute(request) == {'ok': True}
    assert request.execute.call_count == 2


def test_429_429_success_uses_increasing_waits_and_jitter(monkeypatch):
    request = Mock()
    request.execute.side_effect = [http_error(429), http_error(429), {'ok': True}]
    sleep, jitter = Mock(), Mock(side_effect=[0.25, 0.75])
    monkeypatch.setattr('app.services.google_request.time.sleep', sleep)
    monkeypatch.setattr('app.services.google_request.random.random', jitter)
    assert execute(request) == {'ok': True}
    assert request.execute.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1.25, 2.75]
    assert jitter.call_count == 2


def test_exhausted_429_is_controlled_and_not_cached(monkeypatch, system):
    from app import create_app
    request = Mock()
    request.execute.side_effect = http_error(429)
    sleep, jitter = Mock(), Mock(side_effect=[0.25, 0.5, 0.75])
    monkeypatch.setattr('app.services.google_request.time.sleep', sleep)
    monkeypatch.setattr('app.services.google_request.random.random', jitter)
    read = Mock(side_effect=lambda *args, **kwargs: execute(request))
    monkeypatch.setattr(system.sheets, 'read', read)
    client = create_app({'TESTING': True}, {'inventory': system.inventory}).test_client()
    response = client.get('/api/puntos-venta')
    assert response.status_code == 502
    assert response.json == {'correcto': False, 'mensaje': 'Google está recibiendo demasiadas solicitudes. Intente nuevamente.'}
    assert request.execute.call_count == 4
    assert [call.args[0] for call in sleep.call_args_list] == [1.25, 2.5, 4.75]
    assert jitter.call_count == 3
    read.side_effect = None
    read.return_value = system.sheets.books['master']['Control Formularios']
    assert client.get('/api/puntos-venta').json == ['PDV ÁRBOL']
    assert read.call_count == 2


def test_permanent_and_unsafe_requests_not_retried():
    for status, safe in [(403, True), (503, False), (429, False)]:
        request = Mock()
        request.execute.side_effect = http_error(status)
        with pytest.raises(HttpError):
            execute(request, retry_safe=safe)
        assert request.execute.call_count == 1


def test_form_rest_and_adapter_preserve_details():
    auth, adapter = Mock(), Mock()
    api = auth.api.return_value.forms.return_value
    api.create.return_value.execute.return_value = {'formId': 'form'}
    api.setPublishSettings.return_value.execute.side_effect = http_error(403)
    adapter.configure.return_value = {'publishedUrl': 'respond', 'editUrl': 'edit'}
    forms = GoogleFormsService(auth, adapter)
    result = forms.create_inventory_form('PDV', [['', '001', 'Agua', 'X 12']], 'sheet')
    assert result['publishedUrl'] == 'respond'
    items = api.batchUpdate.call_args_list[-1].kwargs['body']['requests']
    assert items[0]['createItem']['item']['title'] == 'Nombre de quien realiza el inventario'
    assert items[1]['createItem']['item']['questionItem']['question']['dateQuestion']['includeYear'] is True
    assert items[2]['createItem']['item']['title'] == 'Productos'
    assert items[3]['createItem']['item']['title'] == '001 – Agua'
    adapter.configure.assert_called_once_with('form', 'sheet')


def test_forms_object_key_order():
    items = GoogleFormsService(Mock(), Mock()).add_products_grouped([['B', '1', 'P', ''], ['10', '2', 'P', ''], ['2', '3', 'P', '']])
    assert [i['title'] for i in items if 'pageBreakItem' in i] == ['2', '10', 'B']


def test_adapter_errors_not_disguised_as_success():
    auth = Mock()
    auth.api.return_value.scripts.return_value.run.return_value.execute.return_value = {'error': {'details': [{'errorMessage': 'Destino denegado'}]}}
    with pytest.raises(FunctionalError, match='Destino denegado'):
        FormsCompatibilityAdapter(auth, 'script').configure('form', 'sheet')


def test_sheets_raw_dates_and_display_are_distinct():
    auth = Mock()
    api = auth.api.return_value.spreadsheets.return_value
    api.get.return_value.execute.return_value = {'properties': {'timeZone': 'America/Bogota'}, 'sheets': [{'data': [{'rowData': [
        {'values': [{'effectiveValue': {'numberValue': 46273}, 'effectiveFormat': {'numberFormat': {'type': 'DATE'}}},
                    {'effectiveValue': {'stringValue': '001'}}]}]}]}]}
    service = GoogleSheetsService(auth)
    row = service.read('book', 'sheet')[0]
    assert isinstance(row[0], datetime)
    assert row[1] == '001'


def test_sheets_views_share_one_get_preserving_formats_and_empty_formula():
    auth = Mock()
    api = auth.api.return_value.spreadsheets.return_value
    api.get.return_value.execute.return_value = {'properties': {'timeZone': 'America/Bogota'}, 'sheets': [{'data': [{'rowData': [
        {'values': [{'effectiveValue': {'numberValue': 46273}, 'formattedValue': '08/09/2026',
                     'effectiveFormat': {'numberFormat': {'type': 'DATE'}}},
                    {'effectiveValue': {'numberValue': 1}, 'formattedValue': '001'},
                    {'effectiveValue': {'numberValue': 2.5}, 'formattedValue': '2,5'}]},
        {'values': []},
        {'values': [{'userEnteredValue': {'formulaValue': '=IF(TRUE,"","")'},
                     'effectiveValue': {'stringValue': ''}, 'formattedValue': ''}]},
        {'values': [{'effectiveFormat': {'numberFormat': {'type': 'NUMBER'}}}]}]}]}]}
    display, raw = GoogleSheetsService(auth).read_views('book', 'sheet')
    assert display == [['08/09/2026', '001', '2,5'], ['', '', ''], ['', '', '']]
    assert isinstance(raw[0][0], datetime)
    assert raw[0][1:] == [1, 2.5]
    assert raw[1:] == [['', '', ''], ['', '', '']]
    api.get.return_value.execute.assert_called_once_with(num_retries=0)


def test_sheets_write_uses_literal_text_and_dates(monkeypatch):
    service = GoogleSheetsService(Mock())
    monkeypatch.setattr(service, 'find_sheet', lambda *args: {'sheetId': 4, 'gridProperties': {'rowCount': 1000, 'columnCount': 26}})
    monkeypatch.setattr(service, 'metadata', lambda book: {'properties': {'timeZone': 'America/Bogota'}})
    batch = Mock()
    monkeypatch.setattr(service, 'batch', batch)
    service.write('book', 'sheet', 2, [['001', '=formula', datetime(2026, 9, 8, tzinfo=ZoneInfo('America/Bogota')), 27]])
    requests = batch.call_args.args[1]
    cells = requests[0]['updateCells']['rows'][0]['values']
    assert cells[0]['userEnteredValue'] == {'stringValue': '001'}
    assert cells[1]['userEnteredValue'] == {'stringValue': '=formula'}
    assert isinstance(cells[2]['userEnteredValue']['numberValue'], float)
    assert requests[1]['repeatCell']['cell']['userEnteredFormat']['numberFormat']['type'] == 'DATE_TIME'

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


def test_permanent_and_unsafe_requests_not_retried():
    for status, safe in [(403, True), (503, False)]:
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

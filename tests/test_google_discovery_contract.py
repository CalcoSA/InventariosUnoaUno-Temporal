"""Valida payloads contra los schemas oficiales distribuidos por Google, sin red."""
import json
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo
from googleapiclient.discovery_cache import get_static_doc
from app.services.google_forms_service import GoogleFormsService
from app.services.google_sheets_service import GoogleSheetsService
from app.services.google_drive_service import GoogleDriveService


def validate(value, schema, document):
    if '$ref' in schema:
        return validate(value, document['schemas'][schema['$ref']], document)
    kind = schema.get('type')
    if kind == 'object':
        assert isinstance(value, dict)
        properties = schema.get('properties', {})
        for key, item in value.items():
            assert key in properties or 'additionalProperties' in schema, f'Campo no documentado: {key}'
            validate(item, properties.get(key, schema.get('additionalProperties', {})), document)
    elif kind == 'array':
        assert isinstance(value, list)
        for item in value:
            validate(item, schema['items'], document)
    elif kind == 'boolean':
        assert isinstance(value, bool)
    elif kind in ('number', 'integer'):
        assert isinstance(value, (int, float))
    elif kind == 'string':
        assert isinstance(value, str)
        if 'enum' in schema:
            assert value in schema['enum']


def test_forms_requests_match_official_discovery():
    document = json.loads(get_static_doc('forms', 'v1'))
    auth, adapter = Mock(), Mock()
    api = auth.api.return_value.forms.return_value
    api.create.return_value.execute.return_value = {'formId': 'form'}
    adapter.configure.return_value = {'publishedUrl': 'r', 'editUrl': 'e'}
    GoogleFormsService(auth, adapter).create_inventory_form('PDV', [['A', '001', 'Agua', 'X 12']], 'book')
    methods = document['resources']['forms']['methods']
    for name in ('create', 'batchUpdate', 'setPublishSettings'):
        for call in getattr(api, name).call_args_list:
            validate(call.kwargs['body'], methods[name]['request'], document)


def test_sheets_requests_match_official_discovery(monkeypatch):
    document = json.loads(get_static_doc('sheets', 'v4'))
    service = GoogleSheetsService(Mock())
    monkeypatch.setattr(service, 'find_sheet', lambda *args: {'sheetId': 1, 'gridProperties': {'rowCount': 1000, 'columnCount': 26}})
    monkeypatch.setattr(service, 'metadata', lambda *args: {'properties': {'timeZone': 'America/Bogota'}})
    batch = Mock()
    monkeypatch.setattr(service, 'batch', batch)
    service.write('book', 'sheet', 2, [['001', 27, datetime(2026, 9, 8, tzinfo=ZoneInfo('America/Bogota'))]])
    service.format_header('book', 'sheet', 12, freeze=True, resize=True)
    for call in batch.call_args_list:
        for request in call.args[1]:
            validate(request, document['schemas']['Request'], document)


def test_drive_conversion_uses_google_import():
    document = json.loads(get_static_doc('drive', 'v3'))
    auth = Mock()
    api = auth.api.return_value.files.return_value
    api.get_media.return_value.execute.return_value = b'xlsx bytes'
    api.create.return_value.execute.return_value = {'id': 'converted'}
    assert GoogleDriveService(auth).convert_xlsx('file', 'PDV', 'folder') == {'id': 'converted'}
    call = api.create.call_args.kwargs
    validate(call['body'], document['schemas']['File'], document)
    assert call['body']['parents'] == ['folder']
    assert call['body']['mimeType'] == 'application/vnd.google-apps.spreadsheet'
    assert call['media_body'].getbytes(0, 10) == b'xlsx bytes'


def test_formula_returning_empty_string_still_occupies_row():
    auth = Mock()
    api = auth.api.return_value.spreadsheets.return_value
    api.get.return_value.execute.return_value = {'sheets': [{'data': [{'rowData': [
        {'values': [{'userEnteredValue': {'stringValue': 'Header'}, 'effectiveValue': {'stringValue': 'Header'}, 'formattedValue': 'Header'}]},
        {'values': []},
        {'values': [{'userEnteredValue': {'formulaValue': '=IF(TRUE,"","")'}, 'effectiveValue': {'stringValue': ''}, 'formattedValue': ''}]},
        {'values': [{'effectiveFormat': {'numberFormat': {'type': 'NUMBER'}}}]}]}]}]}
    assert GoogleSheetsService(auth).read('book', 'sheet', display=True) == [['Header'], [''], ['']]

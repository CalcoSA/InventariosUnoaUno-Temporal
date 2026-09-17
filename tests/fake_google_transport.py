"""Transporte Sheets en RAM: aplica los batches y nunca abre conexiones de red."""
from copy import deepcopy
from threading import Lock, local
import time
from types import SimpleNamespace

import httplib2
from googleapiclient.errors import HttpError

from app.services.google_sheets_service import GoogleSheetsService
from app.utils import js_string


class FakeGoogle:
    def __init__(self, books, latency=0):
        self.books = {}
        self.calls = []
        self.latency = latency
        self.mutex = Lock()
        self.context = local()
        self.failure = None
        self.auth = SimpleNamespace(api=lambda *args, **kwargs: SimpleNamespace(spreadsheets=lambda: self))
        encoder = GoogleSheetsService(None)
        from zoneinfo import ZoneInfo
        for book, sheets in books.items():
            self.books[book] = {'properties': {'timeZone': 'America/Bogota'}, 'sheets': []}
            for sid, (title, rows) in enumerate(sheets.items()):
                cells = encoder._encode_rows(rows, ZoneInfo('America/Bogota'))
                for row in cells:
                    for cell in row['values']:
                        self.effective(cell)
                self.books[book]['sheets'].append({'properties': {
                    'title': title, 'sheetId': sid,
                    'gridProperties': {'rowCount': 1000, 'columnCount': 26}}, 'data': [{'rowData': cells}]})

    @staticmethod
    def effective(cell):
        cell['effectiveValue'] = deepcopy(cell.get('userEnteredValue', {}))
        cell['effectiveFormat'] = deepcopy(cell.get('userEnteredFormat', {}))
        cell['formattedValue'] = js_string(next(iter(cell['effectiveValue'].values()), ''))

    def request(self, method, params, action):
        def execute(num_retries=0):
            assert num_retries == 0
            record = {'method': method, 'book': params['spreadsheetId'],
                      'phase': getattr(self.context, 'phase', ''), 'params': deepcopy(params), 'error': None}
            if self.latency:
                time.sleep(self.latency)
            with self.mutex:
                self.calls.append(record)
                fault = self.failure(record) if self.failure else None
                if fault and not fault.get('after'):
                    record['error'] = fault['status']
                    raise self.error(fault['status'])
                result = action()
                if fault:
                    record['error'] = fault['status']
                    raise self.error(fault['status'])
                return deepcopy(result)
        return SimpleNamespace(execute=execute)

    @staticmethod
    def error(status):
        return HttpError(httplib2.Response({'status': status}), b'{"error":{"message":"simulated private Google error"}}')

    def get(self, **params):
        def action():
            book = deepcopy(self.books[params['spreadsheetId']])
            ranges = params.get('ranges')
            if ranges:
                titles = [value[1:-1].replace("''", "'") for value in ranges]
                if not all(any(s['properties']['title'] == title for s in book['sheets']) for title in titles):
                    raise self.error(400)
                book['sheets'] = [s for s in book['sheets'] if s['properties']['title'] in titles]
            if not params.get('includeGridData'):
                for sheet in book['sheets']:
                    sheet.pop('data', None)
            return book
        return self.request('get', params, action)

    def values(self):
        return self

    def clear(self, **params):
        def action():
            title = params['range'][1:-1].replace("''", "'")
            sheet = next(s for s in self.books[params['spreadsheetId']]['sheets'] if s['properties']['title'] == title)
            for row in sheet['data'][0]['rowData']:
                for cell in row['values']:
                    cell.pop('userEnteredValue', None)
                    self.effective(cell)
            return {}
        return self.request('clear', params, action)

    def batchUpdate(self, **params):
        def action():
            # Emula atomicidad del batch: validar/aplicar a una copia y confirmar al final.
            book = deepcopy(self.books[params['spreadsheetId']])
            replies = [self.apply(book, request) for request in params['body']['requests']]
            self.books[params['spreadsheetId']] = book
            return {'replies': replies}
        return self.request('batchUpdate', params, action)

    def apply(self, book, request):
        if 'addSheet' in request:
            props = deepcopy(request['addSheet']['properties'])
            props.setdefault('sheetId', max((s['properties']['sheetId'] for s in book['sheets']), default=-1) + 1)
            assert all(s['properties']['sheetId'] != props['sheetId'] and s['properties']['title'] != props['title'] for s in book['sheets'])
            props.setdefault('gridProperties', {'rowCount': 1000, 'columnCount': 26})
            book['sheets'].append({'properties': props, 'data': [{'rowData': []}]})
            return {'addSheet': {'properties': deepcopy(props)}}
        kind, details = next(iter(request.items()))
        if kind == 'updateSheetProperties':
            props = details['properties']
            sheet = next(s for s in book['sheets'] if s['properties']['sheetId'] == props['sheetId'])
            for key, value in props.items():
                if isinstance(value, dict):
                    sheet['properties'].setdefault(key, {}).update(deepcopy(value))
                else:
                    sheet['properties'][key] = value
            return {}
        if kind == 'autoResizeDimensions':
            return {}  # No hay píxeles; el payload se verifica por separado.
        assert kind in ('updateCells', 'repeatCell'), kind
        bounds = details.get('start', details.get('range'))
        sheet = next(s for s in book['sheets'] if s['properties']['sheetId'] == bounds['sheetId'])
        grid = sheet['data'][0]['rowData']
        sr = bounds.get('rowIndex', bounds.get('startRowIndex', 0))
        sc = bounds.get('columnIndex', bounds.get('startColumnIndex', 0))
        if kind == 'repeatCell':
            er = bounds.get('endRowIndex', len(grid))
            ec = bounds.get('endColumnIndex', sheet['properties']['gridProperties']['columnCount'])
            source = [[deepcopy(details['cell']) for _ in range(ec - sc)] for _ in range(er - sr)]
        else:
            source = [r.get('values', []) for r in details.get('rows', [])]
            er = bounds.get('endRowIndex', sr + len(source) if 'start' in details else len(grid))
            ec = bounds.get('endColumnIndex', sheet['properties']['gridProperties']['columnCount'])
        assert er <= sheet['properties']['gridProperties']['rowCount']
        while len(grid) < er:
            grid.append({'values': []})
        for ri in range(sr, er):
            incoming = source[ri - sr] if ri - sr < len(source) else []
            # updateCells con range limpia los campos del resto del rango.
            end = ec if 'range' in details or kind == 'repeatCell' else sc + len(incoming)
            assert end <= sheet['properties']['gridProperties']['columnCount']
            values = grid[ri]['values']
            while len(values) < end:
                values.append({})
            for ci in range(sc, end):
                cell = incoming[ci - sc] if ci - sc < len(incoming) else {}
                fields = details['fields'].split(',')
                if 'userEnteredValue' in fields:
                    if 'userEnteredValue' in cell:
                        values[ci]['userEnteredValue'] = deepcopy(cell['userEnteredValue'])
                    else:
                        values[ci].pop('userEnteredValue', None)
                for field in fields:
                    if field.startswith('userEnteredFormat.'):
                        name = field.split('.', 1)[1]
                        fmt = values[ci].setdefault('userEnteredFormat', {})
                        if name in cell.get('userEnteredFormat', {}):
                            fmt[name] = deepcopy(cell['userEnteredFormat'][name])
                self.effective(values[ci])
        return {}

    def rows(self, book, title):
        sheet = next(s for s in self.books[book]['sheets'] if s['properties']['title'] == title)
        return GoogleSheetsService(None)._decode_rows({
            'properties': self.books[book]['properties'], 'sheets': [deepcopy(sheet)]}, False)

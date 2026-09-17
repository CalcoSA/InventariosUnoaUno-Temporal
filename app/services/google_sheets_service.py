from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from app.services.google_request import execute
from app.utils import normalize, normalize_simple


def column_name(index):
    result = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def quoted(title):
    return "'" + title.replace("'", "''") + "'"


class GoogleSheetsService:
    def __init__(self, auth, timezone='America/Bogota'):
        self.auth, self.timezone = auth, timezone

    def api(self):
        return self.auth.api('sheets', 'v4').spreadsheets()

    def metadata(self, book):
        return execute(self.api().get(spreadsheetId=book, fields='spreadsheetId,spreadsheetUrl,properties,sheets.properties'))

    def find_sheet(self, book, name, normalized=False, simple=False):
        normalizer = normalize_simple if simple else normalize
        for sheet in self.metadata(book).get('sheets', []):
            props = sheet['properties']
            if (normalizer(props['title']) == normalizer(name)) if normalized else (props['title'] == name):
                return props
        return None

    def batch(self, book, requests, retry_safe=True):
        return execute(self.api().batchUpdate(spreadsheetId=book, body={'requests': requests}), retry_safe)

    def ensure_sheet(self, book, name):
        props = self.find_sheet(book, name)
        if props:
            return props
        return self.batch(book, [{'addSheet': {'properties': {'title': name}}}], retry_safe=False)['replies'][0]['addSheet']['properties']

    def read(self, book, title, display=False):
        return self._decode_rows(self._read_grid(book, title), display)

    def read_views(self, book, title):
        """Valores visibles y tipados de la misma respuesta, sin dos lecturas REST."""
        result = self._read_grid(book, title)
        return self._decode_rows(result, True), self._decode_rows(result, False)

    def _read_grid(self, book, title):
        return execute(self.api().get(spreadsheetId=book, ranges=[quoted(title)], includeGridData=True,
                       fields='properties.timeZone,sheets.data.rowData.values(userEnteredValue,formattedValue,effectiveValue,effectiveFormat.numberFormat)'))

    def _decode_rows(self, result, display):
        # getValues devuelve Date para celdas fecha, no el serial ni un texto localizado.
        tz = ZoneInfo(result.get('properties', {}).get('timeZone', self.timezone))
        rows = []
        last_row = last_col = 0
        for sheet in result.get('sheets', []):
            for grid in sheet.get('data', []):
                for row in grid.get('rowData', []):
                    values = []
                    for index, c in enumerate(row.get('values', []), 1):
                        v = c.get('effectiveValue', {})
                        if c.get('userEnteredValue') or v:
                            last_row = len(rows) + 1
                            last_col = max(last_col, index)
                        value = next(iter(v.values()), '')
                        kind = c.get('effectiveFormat', {}).get('numberFormat', {}).get('type')
                        if 'numberValue' in v and kind in ('DATE', 'DATE_TIME'):
                            value = (datetime(1899, 12, 30) + timedelta(days=value)).replace(tzinfo=tz)
                        if 'errorValue' in v:
                            value = v['errorValue'].get('message', '#ERROR!')
                        if display:
                            value = c.get('formattedValue', '')
                        values.append(value)
                    rows.append(values)
        return [(r + [''] * max(0, last_col - len(r)))[:last_col] for r in rows[:last_row]]

    def write(self, book, title, start_row, rows, start_col=1):
        if not rows:
            return
        return self.write_ranges(book, title, [(start_row, rows, start_col)])

    def write_ranges(self, book, title, updates):
        updates = [(r, rows, c) for r, rows, c in updates if rows]
        if not updates:
            return
        props = self.find_sheet(book, title)
        book_tz = ZoneInfo(self.metadata(book).get('properties', {}).get('timeZone', self.timezone)) if any(
            isinstance(v, datetime) for _, rows, _ in updates for row in rows for v in row) else None
        requests = self._write_requests(props, updates, book_tz)
        for offset in range(0, len(requests), 400):
            self.batch(book, requests[offset:offset + 400])

    def _write_requests(self, props, updates, book_tz):
        """Rangos fijos: repetir el mismo payload no agrega filas ni suma de nuevo."""
        if not updates:
            return []
        requests = []
        grid = props.get('gridProperties', {})
        needed_rows = max(r + len(rows) - 1 for r, rows, c in updates)
        needed_cols = max(c + max(map(len, rows)) - 1 for r, rows, c in updates)
        if needed_rows > grid.get('rowCount', 1000) or needed_cols > grid.get('columnCount', 26):
            requests.append({'updateSheetProperties': {'properties': {'sheetId': props['sheetId'], 'gridProperties': {
                'rowCount': max(needed_rows, grid.get('rowCount', 1000)), 'columnCount': max(needed_cols, grid.get('columnCount', 26))}}, 'fields': 'gridProperties.rowCount,gridProperties.columnCount'}})
        for start_row, rows, start_col in updates:
            cells = self._encode_rows(rows, book_tz)
            requests.append({'updateCells': {'start': {'sheetId': props['sheetId'], 'rowIndex': start_row - 1, 'columnIndex': start_col - 1},
                                             'rows': cells, 'fields': 'userEnteredValue'}})
            date_rows = {}
            for ri, row in enumerate(cells):
                for ci, c in enumerate(row['values']):
                    if 'userEnteredFormat' in c:
                        date_rows.setdefault(ci, []).append(ri)
            for ci, indices in date_rows.items():
                first = previous = indices[0]
                for ri in indices[1:] + [None]:
                    if ri is not None and ri == previous + 1:
                        previous = ri
                        continue
                    requests.append({'repeatCell': {'range': {'sheetId': props['sheetId'], 'startRowIndex': start_row - 1 + first, 'endRowIndex': start_row + previous,
                        'startColumnIndex': start_col - 1 + ci, 'endColumnIndex': start_col + ci}, 'cell': {'userEnteredFormat': {
                            'numberFormat': {'type': 'DATE_TIME', 'pattern': 'dd/MM/yyyy HH:mm:ss'}}}, 'fields': 'userEnteredFormat.numberFormat'}})
                    first = previous = ri
        return requests

    def write_documents(self, book, metadata, documents):
        """Un batch por libro con metadatos frescos del guardado, nunca caché TTL.

        Incluye creación, rangos, limpieza y formato en orden. Las altas no se
        reintentan; los demás requests fijan valores/rangos, sin append ni incrementos.
        """
        properties = [s['properties'] for s in metadata.get('sheets', [])]
        used = {p['sheetId'] for p in properties}
        requests, retry_safe = [], True
        book_tz = ZoneInfo(metadata.get('properties', {}).get('timeZone', self.timezone))
        for document in documents:
            title = document['title']
            props = next((p for p in properties if p['title'] == title), None)
            if props is None and document.get('rename_from'):
                props = next(p for p in properties if p['title'] == document['rename_from'])
                requests.append({'updateSheetProperties': {'properties': {
                    'sheetId': props['sheetId'], 'title': title}, 'fields': 'title'}})
            created = props is None
            if created:
                sid = 0
                while sid in used:
                    sid += 1
                used.add(sid)
                props = {'sheetId': sid, 'title': title, 'gridProperties': {'rowCount': 1000, 'columnCount': 26}}
                requests.append({'addSheet': {'properties': props}})
                retry_safe = False
            if document.get('replace'):
                requests.append({'updateCells': {'range': {'sheetId': props['sheetId']}, 'fields': 'userEnteredValue'}})
            updates = [(r, rows, c) for r, rows, c in document['updates'] if rows]
            requests.extend(self._write_requests(props, updates, book_tz))
            requests.extend(self._header_requests(props, document['columns'],
                freeze=document.get('freeze', False) and props.get('gridProperties', {}).get('frozenRowCount') != 1,
                resize=True, color=created or document.get('format_header', False)))
        if requests:
            # Un único commit atómico por libro; no separar conteos y resumen PDV.
            return self.batch(book, requests, retry_safe=retry_safe)

    def _encode_rows(self, rows, book_tz):
        cells = []
        for row in rows:
            output = []
            for value in row:
                c = {}
                if isinstance(value, (datetime, date)):
                    if isinstance(value, datetime):
                        # Sheets interpreta seriales en el huso del documento.
                        dt = value.astimezone(book_tz).replace(tzinfo=None) if value.tzinfo else value
                    else:
                        dt = datetime.combine(value, datetime.min.time())
                    c = {'userEnteredValue': {'numberValue': (dt - datetime(1899, 12, 30)).total_seconds() / 86400},
                         'userEnteredFormat': {'numberFormat': {'type': 'DATE_TIME', 'pattern': 'dd/MM/yyyy HH:mm:ss'}}}
                elif isinstance(value, bool):
                    c['userEnteredValue'] = {'boolValue': value}
                elif isinstance(value, (int, float)):
                    c['userEnteredValue'] = {'numberValue': value}
                else:
                    # stringValue conserva códigos con ceros y evita interpretar fórmulas del payload.
                    c['userEnteredValue'] = {'stringValue': '' if value is None else str(value)}
                output.append(c)
            cells.append({'values': output})
        return cells

    def append(self, book, title, rows):
        start = len(self.read(book, title, display=True)) + 1
        self.write(book, title, start, rows)
        return start

    def clear(self, book, title, all_format=False):
        if all_format:
            props = self.find_sheet(book, title)
            self.batch(book, [{'updateCells': {'range': {'sheetId': props['sheetId']}, 'fields': 'userEnteredValue,userEnteredFormat,note,dataValidation'}}])
        else:
            execute(self.api().values().clear(spreadsheetId=book, range=quoted(title), body={}))

    def format_header(self, book, title, columns, freeze=False, resize=False, color=True):
        requests = self._header_requests(self.find_sheet(book, title), columns, freeze, resize, color)
        if requests:
            self.batch(book, requests)

    def _header_requests(self, props, columns, freeze=False, resize=False, color=True):
        sid = props['sheetId']
        requests = []
        if color:
            requests.append({'repeatCell': {'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': columns},
                'cell': {'userEnteredFormat': {'backgroundColor': {'red': 74/255, 'green': 43/255, 'blue': 20/255},
                'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}, 'bold': True}}},
                'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat'}})
        if freeze:
            requests.append({'updateSheetProperties': {'properties': {'sheetId': sid, 'gridProperties': {'frozenRowCount': 1}}, 'fields': 'gridProperties.frozenRowCount'}})
        if resize:
            requests.append({'autoResizeDimensions': {'dimensions': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': columns}}})
        return requests

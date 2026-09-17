from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from app.constants import CONTROL_HEADERS, SUMMARY_HEADERS
from app.repositories.master_sheet_repository import MasterSheetRepository
from app.repositories.pdv_sheet_repository import PdvSheetRepository
from app.repositories.general_summary_repository import GeneralSummaryRepository
from app.services.inventory_summary_service import InventorySummaryService
from app.services.inventory_service import InventoryService
from app.services.locking import InventoryLock
from app.utils import normalize, normalize_simple, js_string


class MemorySheets:
    """Doble de pruebas en RAM. Nunca se conecta a Google ni se usa en producción."""
    def __init__(self):
        self.books = {'master': {'Control Formularios': [CONTROL_HEADERS, ['f1', 'PDV ÁRBOL', 'LISTO', 'pdv']]},
                      'pdv': {'Uno a Uno': [['Categoría', 'Item', 'Producto', 'Desc. U.M.', 'Factor U.M.'],
                                           ['BEBIDAS', '001', 'Agua', 'X 12', 120000],
                                           ['BEBIDAS', '002', 'Jugo', 'unidad', 2]]},
                      'general': {'Resumen General': [SUMMARY_HEADERS]}}
        self.calls = []

    def metadata(self, book):
        return {'properties': {'title': book, 'timeZone': 'America/Bogota'}, 'sheets': [{'properties': {'title': title, 'sheetId': i}} for i, title in enumerate(self.books[book])]}

    def find_sheet(self, book, name, normalized=False, simple=False):
        norm = normalize_simple if simple else normalize
        for i, title in enumerate(self.books[book]):
            if (norm(title) == norm(name)) if normalized else (title == name):
                return {'title': title, 'sheetId': i}
        return None

    def ensure_sheet(self, book, title):
        self.books[book].setdefault(title, [])
        return self.find_sheet(book, title)

    def read(self, book, title, display=False):
        rows = deepcopy(self.books[book][title])
        if display:
            rows = [[js_string(v) if v is not None else '' for v in r] for r in rows]
        return rows

    def read_views(self, book, title):
        return self.read(book, title, display=True), self.read(book, title)

    def write(self, book, title, start_row, rows, start_col=1):
        self.calls.append(('write', book, title, start_row, deepcopy(rows), start_col))
        data = self.books[book][title]
        while len(data) < start_row - 1 + len(rows):
            data.append([])
        for i, values in enumerate(rows, start_row - 1):
            data[i] += [''] * max(0, start_col - 1 + len(values) - len(data[i]))
            data[i][start_col-1:start_col-1+len(values)] = deepcopy(values)

    def append(self, book, title, rows):
        row = len(self.books[book][title]) + 1
        self.write(book, title, row, rows)
        return row

    def write_ranges(self, book, title, updates):
        for row, values, column in updates:
            self.write(book, title, row, values, column)

    def write_documents(self, book, metadata, documents):
        for document in documents:
            title = document['title']
            if document.get('rename_from'):
                self.books[book][title] = self.books[book].pop(document['rename_from'])
            self.ensure_sheet(book, title)
            if document.get('replace'):
                self.clear(book, title)
            self.write_ranges(book, title, document['updates'])
            self.format_header(book, title, document['columns'])

    def clear(self, book, title, all_format=False):
        self.calls.append(('clear', book, title, all_format))
        self.books[book][title] = []

    def format_header(self, *args, **kwargs):
        self.calls.append(('format', args, kwargs))

    def batch(self, book, requests, **kwargs):
        for r in requests:
            props = r['updateSheetProperties']['properties']
            previous = list(self.books[book])[props['sheetId']]
            self.books[book][props['title']] = self.books[book].pop(previous)


@pytest.fixture
def system(tmp_path):
    sheets = MemorySheets()
    master = MasterSheetRepository(sheets, 'master')
    pdv = PdvSheetRepository(sheets, master)
    general = GeneralSummaryRepository(sheets, 'general')
    lock = InventoryLock(str(tmp_path / 'inventory.lock'))
    now = lambda: datetime(2026, 9, 8, 12, 0, tzinfo=ZoneInfo('America/Bogota'))
    summary = InventorySummaryService(master, pdv, general, lock, now)
    inventory = InventoryService(master, pdv, summary, lock, now)
    return type('System', (), dict(sheets=sheets, master=master, pdv=pdv, general=general, lock=lock,
                                  now=staticmethod(now), summary=summary, inventory=inventory))()


@pytest.fixture
def payload():
    return {'puntoVenta': 'PDV ÁRBOL', 'fecha': '2026-09-08', 'categoria': 'BEBIDAS',
            'conteos': [{'categoria': 'BEBIDAS', 'item': '001', 'producto': 'Agua', 'udm': 'X 12', 'cerrado': '2', 'abierto': '3'}]}


@pytest.fixture(autouse=True)
def forbid_google(monkeypatch):
    from app.services.google_auth_service import GoogleAuthService
    def blocked(*args, **kwargs):
        raise AssertionError('Una prueba intentó conectarse a Google')
    monkeypatch.setattr(GoogleAuthService, 'api', blocked)

from app.errors import FunctionalError
from app.utils import cell, text, spreadsheet_id
from app.constants import CONTROL_HEADERS
from app.services.read_cache import ReadCache


class MasterSheetRepository:
    def __init__(self, sheets, book_id):
        self.sheets, self.book_id = sheets, book_id
        self._control_cache = ReadCache(ttl=45, max_entries=1)

    def control(self, required=False, *, cached=False):
        # El guardado y las operaciones administrativas mantienen lecturas frescas.
        if cached:
            rows = self._control_cache.get(self.book_id, lambda: self.control())
        elif not self.sheets.find_sheet(self.book_id, 'Control Formularios'):
            rows = []
        else:
            rows = self.sheets.read(self.book_id, 'Control Formularios', display=True)
        if required and len(rows) < 2:
            raise FunctionalError('No se encontró la hoja Control Formularios.')
        return rows

    def ready(self, required=False):
        for row in self.control(required)[1:]:
            pdv, status, url = [text(cell(row, i)).strip() for i in (1, 2, 3)]
            if pdv and status.upper() == 'LISTO' and url:
                yield pdv, spreadsheet_id(url)

    def pdv_book(self, pdv, *, cached=False):
        for row in self.control(required=True, cached=cached)[1:]:
            if text(cell(row, 1)).strip() == pdv and text(cell(row, 2)).strip().upper() == 'LISTO' and cell(row, 3) != '':
                return spreadsheet_id(cell(row, 3))
        raise FunctionalError(f'No se encontró la base disponible para {pdv}.')

    def ensure_control(self):
        if not self.sheets.find_sheet(self.book_id, 'Control Formularios'):
            self.sheets.ensure_sheet(self.book_id, 'Control Formularios')
            self.sheets.write(self.book_id, 'Control Formularios', 1, [CONTROL_HEADERS])
            self.sheets.format_header(self.book_id, 'Control Formularios', 9, freeze=True, color=False)

    def read_udm(self):
        if not self.sheets.find_sheet(self.book_id, 'Base de datos UDM'):
            rows = []
        else:
            rows = self.sheets.read(self.book_id, 'Base de datos UDM')
        if len(rows) < 2:
            raise FunctionalError('No se encontró información en la hoja Base de datos UDM.')
        return rows

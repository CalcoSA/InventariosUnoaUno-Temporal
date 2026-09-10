from app.constants import ITEM_OPTIONS, FACTOR_OPTIONS, UDM_OPTIONS, COUNT_HEADERS, SUMMARY_HEADERS
from app.utils import find_index, cell, text, correct_factor


class PdvSheetRepository:
    def __init__(self, sheets, master):
        self.sheets, self.master = sheets, master

    def book(self, pdv):
        return self.master.pdv_book(pdv)

    def source(self, book):
        return self.sheets.find_sheet(book, 'Uno a Uno', normalized=True)

    def factors(self, book):
        sheet = self.source(book)
        if not sheet:
            return {}
        rows = self.sheets.read(book, sheet['title'])
        if len(rows) < 2:
            return {}
        item = find_index(rows[0], ITEM_OPTIONS)
        factor = find_index(rows[0], FACTOR_OPTIONS)
        udm = find_index(rows[0], UDM_OPTIONS)
        if item == -1 or factor == -1:
            return {}
        result = {}
        for row in rows[1:]:
            key = text(cell(row, item)).strip()
            value = correct_factor(cell(row, udm), cell(row, factor))
            if key and value > 0:
                result[key] = value
        return result

    def counts(self, book):
        return self.sheets.read(book, 'Conteos Inventarios') if self.sheets.find_sheet(book, 'Conteos Inventarios') else []

    def prepare_counts(self, book):
        self.sheets.ensure_sheet(book, 'Conteos Inventarios')
        self.sheets.write(book, 'Conteos Inventarios', 1, [COUNT_HEADERS])
        self.sheets.format_header(book, 'Conteos Inventarios', 12)

    def append_counts(self, book, rows):
        self.sheets.append(book, 'Conteos Inventarios', rows)
        self.sheets.format_header(book, 'Conteos Inventarios', 12, resize=True, color=False)

    def replace_summary(self, book, rows):
        self.sheets.ensure_sheet(book, 'Resumen Inventario')
        self.sheets.clear(book, 'Resumen Inventario')
        self.sheets.write(book, 'Resumen Inventario', 1, [SUMMARY_HEADERS] + rows)
        self.sheets.format_header(book, 'Resumen Inventario', 10, freeze=True, resize=True)

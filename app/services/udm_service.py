import logging
from app.constants import PRODUCT_OPTIONS, UDM_OPTIONS, FACTOR_OPTIONS, UDM_LOG_HEADERS
from app.errors import FunctionalError
from app.utils import normalize, text, cell, find_index, correct_factor


class UdmService:
    def __init__(self, master, pdv, lock, now):
        self.master, self.pdv, self.lock, self.now = master, pdv, lock, now
        self.sheets = pdv.sheets

    def update_all(self):
        with self.lock.acquire():
            source = self.master.read_udm()
            products = {normalize(cell(r, 1)): (text(cell(r, 2)).strip(), correct_factor(cell(r, 2), cell(r, 3)))
                        for r in source[1:] if normalize(cell(r, 1))}
            results = []
            for point, book in self.master.ready(required=True):
                try:
                    count, missing = self.update_pdv(book, products)
                    results.append([self.now(), point, 'ACTUALIZADO', count, len(missing), ' | '.join(missing[:20])])
                except Exception as error:
                    logging.getLogger(__name__).exception('Error actualizando UDM de %s', point)
                    results.append([self.now(), point, 'ERROR', 0, 0, str(error)])
            title, book = 'Registro actualización UDM', self.master.book_id
            self.sheets.ensure_sheet(book, title)
            if not self.sheets.read(book, title):
                self.sheets.write(book, title, 1, [UDM_LOG_HEADERS])
                self.sheets.format_header(book, title, 6)
            if results:
                self.sheets.append(book, title, results)
            return f'Proceso terminado. Se revisaron {len(results)} puntos de venta.'

    def update_pdv(self, book, products):
        sheet = self.pdv.source(book)
        if not sheet:
            raise FunctionalError('No tiene productos en la hoja Uno a Uno.')
        title = sheet['title']
        display = self.sheets.read(book, title, display=True)
        if len(display) < 2:
            raise FunctionalError('No tiene productos en la hoja Uno a Uno.')
        headers = display[0][:]
        width = max(map(len, display))
        headers += [''] * (width - len(headers))
        product_col = find_index(headers, PRODUCT_OPTIONS)
        if product_col == -1:
            raise FunctionalError('No se encontró la columna del producto.')
        udm_col = find_index(headers, UDM_OPTIONS)
        if udm_col == -1:
            udm_col = len(headers)
            headers.append('Desc. U.M.')
        else:
            headers[udm_col] = 'Desc. U.M.'
        self.sheets.write(book, title, 1, [['Desc. U.M.']], udm_col + 1)
        factor_col = find_index(headers, FACTOR_OPTIONS)
        if factor_col == -1:
            factor_col = len(headers)
            self.sheets.write(book, title, 1, [['Factor U.M.']], factor_col + 1)
        raw = self.sheets.read(book, title)
        udms, factors, missing, count = [], [], [], 0
        for i, row in enumerate(display[1:], 1):
            name = text(cell(row, product_col)).strip()
            value = products.get(normalize(name))
            if value:
                udm, factor = value
                count += 1
            else:
                udm, factor = cell(raw[i], udm_col), cell(raw[i], factor_col)
                if name:
                    missing.append(name)
            udms.append([udm])
            factors.append([factor])
        self.sheets.write(book, title, 2, udms, udm_col + 1)
        self.sheets.write(book, title, 2, factors, factor_col + 1)
        return count, missing

from app.constants import FACTOR_OPTIONS
from app.errors import FunctionalError
from app.utils import find_index, cell, text, number_or_zero, correct_factor, summary_key, date_key, spanish_key


class InventorySummaryService:
    def __init__(self, master, pdv, general, lock, now, timezone='America/Bogota'):
        self.master, self.pdv, self.general = master, pdv, general
        self.lock, self.now, self.timezone = lock, now, timezone

    def key(self, record):
        return summary_key(record[0], record[1], record[2], self.timezone)

    def aggregate(self, grouped, record):
        key = self.key(record)
        if not key:
            return
        if key not in grouped:
            grouped[key] = record[:5] + [0, 0, number_or_zero(record[7]) or 1, 0]
            grouped[key][2] = text(record[2]).strip()
        for i in (5, 6, 8):
            grouped[key][i] += number_or_zero(record[i])

    def records_from_counts(self, book, strict=False, fallback_pdv='', data=None):
        data = self.pdv.counts(book) if data is None else data
        if len(data) < 2:
            return []
        options = [['fecha inventario'], ['punto de venta', 'pdv'], ['item', 'codigo', 'cod'],
            ['nombre producto', 'producto'], ['desc u m', 'desc um', 'udm', 'unidad de medida'],
            ['cerrado'], ['abierto'], FACTOR_OPTIONS]
        indexes = [find_index(data[0], opts) for opts in options]
        if strict and -1 in indexes[:7]:
            raise FunctionalError('No se pudieron identificar todas las columnas de Conteos Inventarios.')
        # Si el conteo incluye su factor guardado, el catálogo no se utiliza.
        factors = self.pdv.factors(book) if indexes[7] == -1 else {}
        records = []
        for row in data[1:]:
            values = [cell(row, i) for i in indexes]
            fecha, pdv, item, product, udm, closed, opened, saved = values
            item = text(item).strip()
            if not item:
                continue
            factor = correct_factor(udm, saved) if indexes[7] != -1 else factors.get(item, 1)
            factor = factor if factor > 0 else 1
            closed, opened = number_or_zero(closed), number_or_zero(opened)
            records.append([fecha, fallback_pdv if indexes[1] == -1 else pdv, item, product, udm,
                            closed, opened, factor, closed * factor + opened])
        return records

    def update_pdv_summary(self, book):
        self.pdv.replace_summary(book, self.pdv_summary_rows(book))

    def pdv_summary_rows(self, book, data=None):
        grouped = {}
        for record in self.records_from_counts(book, strict=True, data=data):
            self.aggregate(grouped, record)
        rows = sorted(grouped.values(), key=lambda r: (date_key(r[0], self.timezone), spanish_key(r[2], numeric=True)))
        stamp = self.now()
        # PDV recalcula con el PRIMER factor del grupo; general suma los físicos individuales.
        for r in rows:
            r[8] = r[5] * r[7] + r[6]
        return [r + [stamp] for r in rows]

    def register_general_summary(self, count_rows):
        metadata, previous, rename_from = self.general.load_for_save()
        existing = previous[1:]
        positions = {self.key(r): i for i, r in enumerate(existing) if self.key(r)}
        grouped = {}
        for row in count_rows:
            self.aggregate(grouped, [row[2], row[3], row[5], row[6], row[7], row[8], row[9], row[10], row[11]])
        stamp, additions, updates = self.now(), [], []
        for key, record in grouped.items():
            if key in positions:
                i = positions[key]
                for c in (5, 6, 8):
                    record[c] += number_or_zero(cell(existing[i], c))
                updates.append((i + 2, record + [stamp]))
            else:
                additions.append(record + [stamp])
        self.general.save_changes(metadata, previous, updates, additions, rename_from)

    def rebuild_general_summary(self):
        with self.lock.acquire():
            grouped = {}
            for pdv, book in self.master.ready(required=True):
                for record in self.records_from_counts(book, fallback_pdv=pdv):
                    self.aggregate(grouped, record)
            rows = sorted(grouped.values(), key=lambda r: (date_key(r[0], self.timezone), spanish_key(r[1]), spanish_key(r[2], numeric=True)))
            stamp = self.now()
            self.general.replace([r + [stamp] for r in rows])
            return f'Resumen general reconstruido: {len(rows)} registros.'

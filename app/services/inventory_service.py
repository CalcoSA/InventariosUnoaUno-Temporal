import math
import uuid
from app.constants import ITEM_OPTIONS, PRODUCT_OPTIONS, UDM_OPTIONS, FACTOR_OPTIONS
from app.errors import FunctionalError
from app.models.product import Product
from app.models.inventory_count import InventoryCount
from app.models.inventory_result import InventoryResult
from app.utils import cell, text, js_string, normalize, find_index, correct_factor, convert_number, duplicate_key, spanish_key


class InventoryService:
    def __init__(self, master, pdv, summary, lock, now, timezone='America/Bogota'):
        self.master, self.pdv, self.summary = master, pdv, summary
        self.lock, self.now, self.timezone = lock, now, timezone

    def get_points_of_sale(self):
        names = [text(cell(r, 1)).strip() for r in self.master.control()[1:]
                 if cell(r, 1) != '' and text(cell(r, 2)).strip().upper() == 'LISTO' and cell(r, 3) != '']
        return sorted(set(names), key=spanish_key)

    def get_categories(self, punto_venta):
        return sorted({p['categoria'] for p in self.get_products(punto_venta) if p['categoria'] != ''}, key=spanish_key)

    def get_products(self, punto_venta, categoria=None):
        book = self.pdv.book(punto_venta)
        sheet = self.pdv.source(book)
        if not sheet:
            raise FunctionalError(f'No se encontró la hoja "Uno a Uno" para {punto_venta}.')
        display = self.pdv.sheets.read(book, sheet['title'], display=True)
        if len(display) < 2:
            return []
        raw = self.pdv.sheets.read(book, sheet['title'])
        headers = display[0]
        options = [['categoria'], ITEM_OPTIONS, PRODUCT_OPTIONS,
                   UDM_OPTIONS + ['descripcion unidad de medida', 'um empaque']]
        indexes = [find_index(headers, opt) for opt in options]
        c_cat, c_item, c_product, c_udm = [i if i != -1 else n for n, i in enumerate(indexes)]
        c_factor = find_index(headers, FACTOR_OPTIONS)
        filtered = [r for r in display[1:] if js_string(cell(r, c_item)).strip() and js_string(cell(r, c_product)).strip()]
        result = []
        for position, row in enumerate(filtered):
            # Conserva el índice del map DESPUÉS del filter del legacy, incluso con huecos.
            factor = correct_factor(cell(row, c_udm), cell(raw[position + 1], c_factor) if c_factor != -1 else 1)
            product = Product(position + 1, js_string(cell(row, c_cat)).strip() or 'Uno a Uno',
                js_string(cell(row, c_item)).strip(), js_string(cell(row, c_product)).strip(), js_string(cell(row, c_udm)).strip(), factor)
            if not normalize(categoria) or normalize(product.categoria) == normalize(categoria):
                result.append(product.to_dict())
        return result

    def save_inventory(self, data):
        if not isinstance(data, dict) or not all(data.get(k) for k in ('puntoVenta', 'fecha', 'categoria')):
            raise FunctionalError('Debe seleccionar el PDV, la fecha y la categoría.')
        counts = data.get('conteos')
        if not isinstance(counts, list) or not counts:
            raise FunctionalError('No se recibieron conteos para guardar.')
        if any(not isinstance(c, dict) for c in counts):
            raise FunctionalError('No se recibieron conteos para guardar.')
        valid = [c for c in counts if c.get('cerrado') not in ('', None) or c.get('abierto') not in ('', None)]
        if not valid:
            raise FunctionalError('Debe registrar al menos una cantidad en Cerrado o Abierto.')
        record_id, stamp = str(uuid.uuid4()), self.now()
        book = self.pdv.book(data['puntoVenta'])
        factors = self.pdv.factors(book)
        rows = []
        for c in valid:
            closed, opened = convert_number(c.get('cerrado'), 0), convert_number(c.get('abierto'), 0)
            item = text(c.get('item')).strip()
            factor = factors.get(item, 1)
            factor = factor if factor > 0 else 1
            for value, label in ((closed, 'cerrada'), (opened, 'abierta')):
                if not math.isfinite(value) or value < 0:
                    raise FunctionalError(f'La cantidad {label} del ítem {c.get("item", "undefined")} no es válida.')
            if not math.isfinite(factor) or factor <= 0:
                raise FunctionalError(f'El factor del ítem {c.get("item", "undefined")} no es válido.')
            count = InventoryCount(item, closed, opened, factor)
            if not math.isfinite(count.conteo_fisico):
                raise FunctionalError(f'El conteo físico del ítem {item} no es válido.')
            rows.append([record_id, stamp, data['fecha'], data['puntoVenta'], data['categoria'],
                         c.get('item', ''), c.get('producto', ''), c.get('udm', ''), closed, opened, factor, count.conteo_fisico])
        with self.lock.acquire():
            self.pdv.prepare_counts(book)
            key = duplicate_key(data['fecha'], data['puntoVenta'], data['categoria'], self.timezone)
            if any(duplicate_key(cell(r, 2), cell(r, 3), cell(r, 4), self.timezone) == key for r in self.pdv.counts(book)[1:]):
                raise FunctionalError(f'La categoría "{data["categoria"]}" ya fue guardada para {data["puntoVenta"]} en esta fecha.')
            self.pdv.append_counts(book, rows)
            self.summary.update_pdv_summary(book)
            self.summary.register_general_summary(rows)
        return InventoryResult(len(rows)).to_dict()

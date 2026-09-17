"""Simular guardados: python -B tests/tools/save_load.py --latency 0.1

Usa Flask test client, InventoryLock y GoogleSheetsService reales, con transporte
Google íntegramente simulado. No inicia servidores ni lee credenciales.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Barrier, Lock
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from app import create_app
from app.constants import CONTROL_HEADERS, COUNT_HEADERS, SUMMARY_HEADERS
from app.repositories.master_sheet_repository import MasterSheetRepository
from app.repositories.pdv_sheet_repository import PdvSheetRepository
from app.repositories.general_summary_repository import GeneralSummaryRepository
from app.services.google_sheets_service import GoogleSheetsService
from app.services.inventory_service import InventoryService
from app.services.inventory_summary_service import InventorySummaryService
from app.services.locking import InventoryLock
from fake_google_transport import FakeGoogle


class MeasuredLock(InventoryLock):
    def __init__(self, path):
        super().__init__(path)
        self.waits = []
        self.holds = []
        self.mutex = Lock()

    @contextmanager
    def acquire(self, timeout=30):
        start = time.perf_counter()
        entered = False
        try:
            with super().acquire(timeout=timeout):
                acquired = time.perf_counter()
                entered = True
                with self.mutex:
                    self.waits.append(acquired - start)
                try:
                    yield
                finally:
                    with self.mutex:
                        self.holds.append(time.perf_counter() - acquired)
        finally:
            if not entered:
                with self.mutex:
                    self.waits.append(time.perf_counter() - start)


def build_system(path, users, latency=0, same_book=False, duplicate=False, products=1):
    books = {'master': {'Control Formularios': [CONTROL_HEADERS]}, 'general': {'Resumen General': [SUMMARY_HEADERS]}}
    payloads = []
    for i in range(users):
        index = 0 if same_book or duplicate else i
        book, pdv = f'pdv-{index}', f'PDV {index:02}'
        if book not in books:
            books['master']['Control Formularios'].append(['', pdv, 'LISTO', book])
            books[book] = {'Uno a Uno': [['Categoria', 'Item', 'Producto', 'Desc. U.M.', 'Factor U.M.']] + [
                ['Bodega', f'{item + 1:03}', 'Producto', 'X 12', 12] for item in range(products)],
                'Conteos Inventarios': [COUNT_HEADERS], 'Resumen Inventario': [SUMMARY_HEADERS]}
        payloads.append({'puntoVenta': pdv, 'fecha': '2026-09-17', 'categoria': 'Bodega' if duplicate else f'Categoria {i}',
            'conteos': [{'item': f'{item + 1:03}', 'producto': 'Producto', 'udm': 'X 12', 'cerrado': 2, 'abierto': 3}
                        for item in range(products)]})
    google = FakeGoogle(books, latency)
    sheets = GoogleSheetsService(google.auth)
    master = MasterSheetRepository(sheets, 'master')
    pdv = PdvSheetRepository(sheets, master)
    general = GeneralSummaryRepository(sheets, 'general')
    lock = MeasuredLock(str(path / 'inventory.lock'))
    now = lambda: datetime(2026, 9, 17, 12, tzinfo=ZoneInfo('America/Bogota'))
    summary = InventorySummaryService(master, pdv, general, lock, now)
    inventory = InventoryService(master, pdv, summary, lock, now)
    for obj, methods in [(master, ['pdv_book']), (pdv, ['factors', 'prepare_counts', 'counts', 'append_counts', 'replace_summary',
                                                   'load_for_save', 'save_counts_and_summary']),
                         (general, ['prepare', 'rows', 'update_many', 'append', 'format', 'load_for_save', 'save_changes'])]:
        for method in methods:
            original = getattr(obj, method)
            def wrapped(*args, _original=original, _phase=type(obj).__name__ + '.' + method, **kwargs):
                previous = getattr(google.context, 'phase', '')
                google.context.phase = _phase
                try:
                    return _original(*args, **kwargs)
                finally:
                    google.context.phase = previous
            setattr(obj, method, wrapped)
    app = create_app({'TESTING': True}, {'inventory': inventory})
    return google, inventory, lock, app, payloads


def run(users, latency=0.1, same_book=False, duplicate=False, products=1, initial_429=0):
    with TemporaryDirectory(prefix='inventory-save-load-') as directory:
        google, inventory, lock, app, payloads = build_system(Path(directory), users, latency, same_book, duplicate, products)
        failures = 0
        def fail(call):
            nonlocal failures
            if call['method'] == 'batchUpdate' and failures < initial_429:
                failures += 1
                return {'status': 429}
        google.failure = fail
        start = Barrier(users)
        def save(payload):
            with app.test_client() as client:
                start.wait(timeout=15)
                began = time.perf_counter()
                response = client.post('/api/inventarios', json=payload)
                return {'status': response.status_code, 'body': response.json, 'seconds': time.perf_counter() - began}
        began = time.perf_counter()
        with ThreadPoolExecutor(max_workers=users) as pool:
            results = list(pool.map(save, payloads))
        total = time.perf_counter() - began
        saved = sum(len(google.rows(book, 'Conteos Inventarios')) - 1 for book in google.books if book.startswith('pdv-'))
        successes = sum(result['status'] == 200 for result in results)
        assert saved == successes * products, (saved, successes)
        physical = sum(row[8] for row in google.rows('general', 'Resumen General')[1:])
        assert physical == successes * products * 27, (physical, successes)
        all_ids = []
        pdv_physical = 0
        for book in google.books:
            if book.startswith('pdv-'):
                rows = google.rows(book, 'Conteos Inventarios')[1:]
                assert all(row[10:] == [12, 27] for row in rows)
                all_ids.extend(row[0] for row in rows)
                pdv_physical += sum(row[8] for row in google.rows(book, 'Resumen Inventario')[1:])
        assert len(set(all_ids)) == successes
        assert pdv_physical == physical
        return {'users': users, 'products': products, 'success': successes, 'failures': users - successes,
            'seconds': round(total, 3), 'max_request': round(max(r['seconds'] for r in results), 3),
            'max_wait': round(max(lock.waits), 3), 'max_hold': round(max(lock.holds, default=0), 3),
            'calls': len(google.calls), 'lock_timeouts': sum('bloqueo' in r['body'].get('mensaje', '') for r in results),
            'duplicates': sum('ya fue guardada' in r['body'].get('mensaje', '') for r in results),
            '429': sum(c['error'] == 429 for c in google.calls),
            'phases': dict(Counter(c['phase'] for c in google.calls)),
            'requests': [round(r['seconds'], 3) for r in results]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--latency', type=float, default=0.1, help='Segundos simulados por llamada Google; no es latencia medida en producción.')
    parser.add_argument('--users', type=int, nargs='+', default=[1, 5, 10, 20, 36, 40])
    parser.add_argument('--products', type=int, default=1)
    parser.add_argument('--initial-429', type=int, default=0, help='Fallos transitorios al comienzo de las escrituras; retries con esperas reales.')
    parser.add_argument('--same-book', action='store_true')
    parser.add_argument('--duplicate', action='store_true')
    args = parser.parse_args()
    for users in args.users:
        print(json.dumps(run(users, args.latency, args.same_book, args.duplicate, args.products, args.initial_429)), flush=True)

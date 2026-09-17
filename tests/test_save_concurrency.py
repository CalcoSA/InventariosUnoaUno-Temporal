from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from unittest.mock import Mock
from threading import Barrier
from types import SimpleNamespace

import pytest
from googleapiclient.discovery_cache import get_static_doc

from app.constants import COUNT_HEADERS, SUMMARY_HEADERS
from test_google_discovery_contract import validate
from tools.save_load import build_system, run


@pytest.mark.parametrize('users', [1, 5, 10, 20, 36, 40])
def test_distinct_saves_keep_all_counts_and_summaries(users):
    result = run(users, latency=0)
    assert result['success'] == users
    assert result['failures'] == result['lock_timeouts'] == result['duplicates'] == result['429'] == 0
    assert result['calls'] == users * 10


def test_same_pdv_distinct_categories_and_duplicates():
    assert run(36, latency=0, same_book=True)['success'] == 36
    result = run(36, latency=0, duplicate=True)
    assert result['success'] == 1
    assert result['duplicates'] == 35
    assert result['lock_timeouts'] == 0
    assert result['calls'] == 10 + 35 * 6  # Rechazo fresco, sin escrituras ni formatos.


def test_real_batch_payloads_match_discovery_and_fixed_ranges(tmp_path):
    google, inventory, lock, app, payloads = build_system(tmp_path, 1)
    assert app.test_client().post('/api/inventarios', json=payloads[0]).status_code == 200
    batches = [c for c in google.calls if c['method'] == 'batchUpdate']
    assert len(batches) == 2
    document = json.loads(get_static_doc('sheets', 'v4'))
    for batch in batches:
        for request in batch['params']['body']['requests']:
            validate(request, document['schemas']['Request'], document)
            assert 'appendCells' not in request
    assert google.rows('pdv-0', 'Conteos Inventarios')[1][10:] == [12, 27]
    assert google.rows('pdv-0', 'Resumen Inventario')[1][5:9] == [2, 3, 12, 27]
    assert google.rows('general', 'Resumen General')[1][5:9] == [2, 3, 12, 27]
    # La segunda escritura al mismo libro mantiene el formato ya configurado.
    payload = deepcopy(payloads[0])
    payload['categoria'] = 'Otra'
    assert app.test_client().post('/api/inventarios', json=payload).status_code == 200
    batches = [c for c in google.calls if c['method'] == 'batchUpdate'][-2:]
    for batch in batches:
        assert not any('textFormat' in str(r) for r in batch['params']['body']['requests'])
        assert not any('frozenRowCount' in str(r) for r in batch['params']['body']['requests'])


@pytest.mark.parametrize('general_first', [None, 'empty', 'occupied'])
def test_missing_sheets_created_and_general_first_sheet_preserved(tmp_path, general_first):
    google, inventory, lock, app, payloads = build_system(tmp_path, 1)
    google.books['pdv-0']['sheets'] = google.books['pdv-0']['sheets'][:1]
    if general_first is None:
        google.books['general']['sheets'] = []
    else:
        sheet = google.books['general']['sheets'][0]
        sheet['properties']['title'] = 'Hoja 1'
        sheet['data'][0]['rowData'] = [] if general_first == 'empty' else sheet['data'][0]['rowData']
    assert app.test_client().post('/api/inventarios', json=payloads[0]).status_code == 200
    assert google.rows('pdv-0', 'Conteos Inventarios')[0] == COUNT_HEADERS
    assert google.rows('pdv-0', 'Resumen Inventario')[0] == SUMMARY_HEADERS
    assert google.rows('general', 'Resumen General')[0] == SUMMARY_HEADERS
    titles = [s['properties']['title'] for s in google.books['general']['sheets']]
    assert ('Hoja 1' in titles) == (general_first == 'occupied')
    assert len(google.rows('general', 'Resumen General')) == 2
    for book in ('pdv-0', 'general'):
        for sheet in google.books[book]['sheets']:
            if sheet['properties']['title'] in ('Conteos Inventarios', 'Resumen Inventario', 'Resumen General'):
                assert sheet['data'][0]['rowData'][0]['values'][0]['userEnteredFormat']['textFormat']['bold']


def test_grows_grid_and_clears_old_summary_tail(tmp_path):
    google, inventory, lock, app, payloads = build_system(tmp_path, 1)
    for book in ('pdv-0', 'general'):
        for sheet in google.books[book]['sheets']:
            if sheet['properties']['title'] != 'Uno a Uno':
                sheet['properties']['gridProperties'] = {'rowCount': 1, 'columnCount': 1}
    assert app.test_client().post('/api/inventarios', json=payloads[0]).status_code == 200
    sheet = next(s for s in google.books['pdv-0']['sheets'] if s['properties']['title'] == 'Resumen Inventario')
    sheet['properties']['gridProperties']['rowCount'] = 5
    sheet['data'][0]['rowData'].extend(deepcopy(sheet['data'][0]['rowData'][1:]) * 3)
    payloads[0]['categoria'] = 'Otra'
    assert app.test_client().post('/api/inventarios', json=payloads[0]).status_code == 200
    assert len(google.rows('pdv-0', 'Resumen Inventario')) == 2
    assert google.rows('pdv-0', 'Resumen Inventario')[1][5:9] == [4, 6, 12, 54]


@pytest.mark.parametrize('method,after', [('get', False), ('batchUpdate', False), ('batchUpdate', True)])
def test_transient_429_and_ambiguous_committed_write_keep_uuid_and_totals(tmp_path, monkeypatch, method, after):
    google, inventory, lock, app, payloads = build_system(tmp_path, 1)
    sleep = Mock()
    monkeypatch.setattr('app.services.google_request.time', SimpleNamespace(sleep=sleep))
    monkeypatch.setattr('app.services.google_request.random.random', lambda: 0.25)
    failures = 0
    def fail(call):
        nonlocal failures
        if call['method'] == method and failures < 2:
            failures += 1
            return {'status': 503 if after else 429, 'after': after}
    google.failure = fail
    assert app.test_client().post('/api/inventarios', json=payloads[0]).status_code == 200
    assert [c.args[0] for c in sleep.call_args_list] == [1.25, 2.25]
    assert len(google.rows('pdv-0', 'Conteos Inventarios')) == 2
    assert google.rows('general', 'Resumen General')[1][8] == 27
    if method == 'batchUpdate':
        retries = [c['params']['body'] for c in google.calls if c['method'] == method][:3]
        assert retries[0] == retries[1] == retries[2]  # Mismo UUID, mismos rangos, mismos totales.


def test_permanent_429_is_controlled_and_creation_is_not_retried(tmp_path, monkeypatch):
    google, inventory, lock, app, payloads = build_system(tmp_path, 1)
    monkeypatch.setattr('app.services.google_request.time', SimpleNamespace(sleep=Mock()))
    google.failure = lambda call: {'status': 429} if call['method'] == 'get' else None
    response = app.test_client().post('/api/inventarios', json=payloads[0])
    assert response.status_code == 502
    assert 'demasiadas solicitudes' in response.json['mensaje']
    assert 'private' not in response.text
    assert len(google.calls) == 4
    assert len(google.rows('pdv-0', 'Conteos Inventarios')) == 1
    google.calls.clear()
    google.books['pdv-0']['sheets'] = google.books['pdv-0']['sheets'][:1]
    google.failure = lambda call: {'status': 503, 'after': True} if call['method'] == 'batchUpdate' else None
    response = app.test_client().post('/api/inventarios', json=payloads[0])
    assert response.status_code == 502
    assert Counter(c['method'] for c in google.calls)['batchUpdate'] == 1
    assert len(google.rows('pdv-0', 'Conteos Inventarios')) == 2
    google.failure = None
    assert app.test_client().post('/api/inventarios', json=payloads[0]).status_code == 400


def test_36_saves_recover_from_429_on_each_pdv_and_general(tmp_path, monkeypatch):
    google, inventory, lock, app, payloads = build_system(tmp_path, 36)
    sleep = Mock()
    monkeypatch.setattr('app.services.google_request.time', SimpleNamespace(sleep=sleep))
    monkeypatch.setattr('app.services.google_request.random.random', lambda: 0.25)
    failures = Counter()
    def fail(call):
        book = call['book']
        if call['method'] == 'batchUpdate' and failures[book] < 2:
            failures[book] += 1
            return {'status': 429}
    google.failure = fail
    start = Barrier(36)
    def save(payload):
        start.wait(timeout=10)
        return app.test_client().post('/api/inventarios', json=payload).status_code
    with ThreadPoolExecutor(max_workers=36) as pool:
        assert list(pool.map(save, payloads)) == [200] * 36
    assert sum(c['error'] == 429 for c in google.calls) == 74
    assert sleep.call_count == 74
    assert len(google.calls) == 434
    assert len(google.rows('general', 'Resumen General')) == 37
    assert sum(row[8] for row in google.rows('general', 'Resumen General')[1:]) == 36 * 27
    assert all(len(google.rows(f'pdv-{i}', 'Conteos Inventarios')) == 2 for i in range(36))


def test_sustained_quota_exhaustion_cannot_be_promised_as_success(tmp_path, monkeypatch):
    google, inventory, lock, app, payloads = build_system(tmp_path, 36)
    monkeypatch.setattr('app.services.google_request.time', SimpleNamespace(sleep=Mock()))
    usage = Counter()
    def quota(call):
        kind = 'read' if call['method'] == 'get' else 'write'
        if usage[kind] >= 60:
            return {'status': 429}
        usage[kind] += 1
    google.failure = quota
    # Una ventana de cuota agotada que no se repone durante estos retries.
    responses = [app.test_client().post('/api/inventarios', json=payload) for payload in payloads]
    assert sum(response.status_code == 200 for response in responses) == 7
    assert all(response.status_code == 502 for response in responses[7:])
    assert all('demasiadas solicitudes' in response.json['mensaje'] for response in responses[7:])
    assert not any('private' in response.text for response in responses)


def test_general_failure_reports_partial_save_without_repeating_counts(tmp_path, monkeypatch):
    google, inventory, lock, app, payloads = build_system(tmp_path, 1)
    monkeypatch.setattr('app.services.google_request.time', SimpleNamespace(sleep=Mock()))
    google.failure = lambda call: {'status': 429} if call['book'] == 'general' else None
    response = app.test_client().post('/api/inventarios', json=payloads[0])
    assert response.status_code == 502
    # Dos libros no forman una transacción: nunca responder éxito si falló el general.
    assert len(google.rows('pdv-0', 'Conteos Inventarios')) == 2
    assert google.rows('pdv-0', 'Resumen Inventario')[1][8] == 27
    assert len(google.rows('general', 'Resumen General')) == 1
    google.failure = None
    assert app.test_client().post('/api/inventarios', json=payloads[0]).status_code == 400
    assert len(google.rows('pdv-0', 'Conteos Inventarios')) == 2

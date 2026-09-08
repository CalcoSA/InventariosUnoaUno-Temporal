import json
from pathlib import Path
import re
import shutil
import subprocess
from copy import deepcopy
from datetime import datetime
import pytest
from app.utils import normalize, normalize_simple, correct_factor, date_key, summary_key, spanish_key


def node():
    binary = shutil.which('node')
    if not binary:
        pytest.skip('Node.js requerido solo para comparar con el legacy y ejecutar smoke JS')
    return binary


def test_differential_against_original_javascript():
    cases = []
    for value in ['Categoría', 'PDV ÁRBOL', 'Desc. U.M.', 'Factor_U.M.', 'Á.-__ B', '', None, 0]:
        cases.append(('normalizar_', [value], normalize(value)))
        cases.append(('normalizarTexto_', [value], normalize_simple(value)))
    for udm in ['X 12', 'x6', 'X 2,5', 'X 0', '', 'unidad', 'X 10000', 'X 2.5.6']:
        for factor in ['', 1, 0, -1, 120000, 1200000000, '2,5', 'texto']:
            cases.append(('obtenerFactorCorrecto_', [udm, factor], correct_factor(udm, factor)))
    for value in ['8/9/2026', '08-09-2026', '2026-09-08', 'unknown', '']:
        cases.append(('claveFecha_', [value], date_key(value)))
    for pdv in ['PDV ÁRBOL', 'pdv arbol']:
        cases.append(('claveResumenGeneral_', ['8/9/2026', pdv, '001'], summary_key('8/9/2026', pdv, '001')))
    result = subprocess.run([node(), 'tests/legacy_reference.cjs'], input=json.dumps([{'fn': fn, 'args': args} for fn, args, _ in cases]),
                            capture_output=True, text=True, encoding='utf-8', check=True)
    assert json.loads(result.stdout) == [expected for _, _, expected in cases]


def test_frontend_flows():
    result = subprocess.run([node(), 'tests/frontend_smoke.cjs'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('numeric', [False, True])
def test_spanish_collation_against_javascript(numeric):
    values = ['1', '2', '10', '001', '01', 'a2', 'a10', 'A2', '-1', '_2', 'á2', 'a1', 'ñ1', 'n2', 'Nube', 'Ñame', 'Oso', 'Árbol']
    result = subprocess.run([node(), 'tests/legacy_reference.cjs'], input=json.dumps([{'fn': 'sort', 'args': [values, numeric]}]),
        capture_output=True, text=True, encoding='utf-8', check=True)
    assert sorted(values, key=lambda v: spanish_key(v, numeric)) == json.loads(result.stdout)[0]


def test_original_css_and_markup_unchanged():
    original = Path('legacy/Index.html').read_text(encoding='utf-8')
    migrated = Path('app/templates/index.html').read_text(encoding='utf-8')
    assert re.search(r'<style>([\s\S]*?)</style>', original)[1] == Path('app/static/css/inventory.css').read_text(encoding='utf-8')
    body = lambda s: re.sub(r'<script[\s\S]*?</script>', '', s.split('<body>')[1])
    assert body(original) == body(migrated)
    assert 'google.script.run' not in Path('app/static/js/inventory.js').read_text(encoding='utf-8')


@pytest.mark.parametrize('operation', ['save', 'rebuild', 'udm'])
def test_workflows_against_original_appsscript(system, payload, operation):
    if operation == 'save':
        function, args = 'guardarInventario', [payload]
        action = lambda: system.inventory.save_inventory(payload)
    elif operation == 'rebuild':
        from app.constants import COUNT_HEADERS
        system.sheets.books['pdv']['Conteos Inventarios'] = [COUNT_HEADERS,
            ['old', '', '08/09/2026', 'PDV ÁRBOL', 'A', '001', 'Agua', 'X 6', 2, 1, 6, 999],
            ['old2', '', '2026-09-08', 'pdv arbol', 'B', '001', 'Agua', 'X 12', 1, 2, 12, 999]]
        function, args = 'reconstruirResumenGeneral', []
        action = system.summary.rebuild_general_summary
    else:
        from app.services.udm_service import UdmService
        system.sheets.books['master']['Base de datos UDM'] = [['', '', '', '', ''], ['', 'AGUA', 'X 6', 60000, '']]
        function, args = 'actualizarTodasLasBasesUDM', []
        action = UdmService(system.master, system.pdv, system.lock, system.now).update_all
    original = subprocess.run([node(), 'tests/legacy_inventory.cjs'], input=json.dumps({'books': system.sheets.books, 'function': function, 'args': args}),
                             capture_output=True, text=True, encoding='utf-8', check=True)
    result = action()
    books = deepcopy(system.sheets.books)
    if operation == 'save':
        for row in books['pdv']['Conteos Inventarios'][1:]:
            row[0] = '<UUID>'
    actual = json.loads(json.dumps({'result': result, 'books': books}, default=lambda v: '<DATE>' if isinstance(v, datetime) else str(v)))
    assert actual == json.loads(original.stdout)

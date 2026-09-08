from app.constants import COUNT_HEADERS, SUMMARY_HEADERS


def test_general_increment_is_sum_not_recalculation(system, payload):
    system.sheets.books['general']['Resumen General'].append(['08/09/2026', 'pdv arbol', '001', 'Antiguo', 'X 6', 1, 1, 6, 7, ''])
    system.inventory.save_inventory(payload)
    row = system.general.rows()[0]
    assert row[5:9] == [3, 4, 12, 34]
    assert row[3] == 'Agua'


def test_pdv_first_factor_general_sums_individual_physical(system):
    system.sheets.books['pdv']['Conteos Inventarios'] = [COUNT_HEADERS,
        ['a', '', '2026-09-08', 'PDV ÁRBOL', 'A', '001', 'Agua', 'X 6', 1, 1, 6, 999],
        ['b', '', '2026-09-08', 'pdv arbol', 'B', '001', 'Agua', 'X 12', 1, 1, 12, 999]]
    system.summary.update_pdv_summary('pdv')
    assert system.sheets.books['pdv']['Resumen Inventario'][1][5:9] == [2, 2, 6, 14]
    assert system.summary.rebuild_general_summary() == 'Resumen general reconstruido: 1 registros.'
    assert system.general.rows()[0][5:9] == [2, 2, 6, 20]


def test_empty_summary_and_first_sheet_rename(system):
    system.summary.update_pdv_summary('pdv')
    assert system.sheets.books['pdv']['Resumen Inventario'] == [SUMMARY_HEADERS]
    system.sheets.books['general'] = {'Hoja 1': []}
    system.general.prepare()
    assert list(system.sheets.books['general']) == ['Resumen General']


def test_numeric_item_sort(system):
    system.sheets.books['pdv']['Conteos Inventarios'] = [COUNT_HEADERS] + [
        ['id', '', '2026-09-08', 'PDV ÁRBOL', 'A', i, 'P', '', 1, 0, 1, 1] for i in ['10', '2', '1']]
    system.summary.update_pdv_summary('pdv')
    assert [r[2] for r in system.sheets.books['pdv']['Resumen Inventario'][1:]] == ['1', '2', '10']

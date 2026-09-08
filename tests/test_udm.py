from app.services.udm_service import UdmService


def test_udm_adds_columns_preserves_unmatched_and_logs(system):
    system.sheets.books['master']['Base de datos UDM'] = [['ID', 'Producto', 'UDM', 'Factor', 'Extra'], ['1', 'ÁGUA', 'X 6', 60000, '']]
    system.sheets.books['pdv']['Uno a Uno'] = [['Categoría', 'Item', 'Producto'], ['A', '001', 'agua'], ['A', '002', 'Sin coincidencia']]
    result = UdmService(system.master, system.pdv, system.lock, system.now).update_all()
    assert result == 'Proceso terminado. Se revisaron 1 puntos de venta.'
    rows = system.sheets.books['pdv']['Uno a Uno']
    assert rows[0][-2:] == ['Desc. U.M.', 'Factor U.M.']
    assert rows[1][-2:] == ['X 6', 6]
    log = system.sheets.books['master']['Registro actualización UDM'][-1]
    assert log[2:] == ['ACTUALIZADO', 1, 1, 'Sin coincidencia']


def test_udm_error_does_not_stop_other_pdv(system):
    system.sheets.books['master']['Base de datos UDM'] = [['', '', '', '', ''], ['', 'Agua', 'X 12', 12, '']]
    system.sheets.books['master']['Control Formularios'].append(['bad', 'PDV MALO', 'LISTO', 'bad'])
    system.sheets.books['bad'] = {}
    assert '2 puntos de venta' in UdmService(system.master, system.pdv, system.lock, system.now).update_all()
    assert [r[2] for r in system.sheets.books['master']['Registro actualización UDM'][1:]] == ['ACTUALIZADO', 'ERROR']


def test_udm_missing_truncated_and_preserves_previous(system):
    system.sheets.books['master']['Base de datos UDM'] = [['', '', '', '', ''], ['', 'different', '', 1, '']]
    system.sheets.books['pdv']['Uno a Uno'] = [['Producto', 'UDM', 'Factor']] + [[f'P{i}', 'viejo', 7] for i in range(25)]
    UdmService(system.master, system.pdv, system.lock, system.now).update_all()
    log = system.sheets.books['master']['Registro actualización UDM'][-1]
    assert log[4] == 25
    assert len(log[5].split(' | ')) == 20
    assert system.sheets.books['pdv']['Uno a Uno'][1][1:] == ['viejo', 7]

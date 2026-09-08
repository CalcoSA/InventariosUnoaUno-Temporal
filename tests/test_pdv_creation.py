from unittest.mock import Mock
from app.constants import MIME_XLSX
from app.services.pdv_creation_service import PdvCreationService
from app.services.locking import InventoryLock


def creation(system, tmp_path):
    drive, forms, sleep = Mock(), Mock(), Mock()
    drive.parent.return_value = 'folder'
    drive.list_files.side_effect = lambda folder: iter([
        {'id': 'master-xlsx', 'name': 'master.xlsx', 'mimeType': MIME_XLSX},
        {'id': 'bad-xlsx', 'name': 'Malo.xlsx', 'mimeType': MIME_XLSX},
        {'id': 'good-xlsx', 'name': 'Bueno.XLSX', 'mimeType': MIME_XLSX},
        {'id': 'ignore', 'name': 'PDF', 'mimeType': 'application/pdf'}])
    drive.convert_xlsx.side_effect = [RuntimeError('Conversión fallida'), {'id': 'converted'}]
    system.sheets.books['converted'] = {'Uno a Uno': [['Cat', 'Item', 'Producto', 'UDM'], ['A', '1', 'Agua', 'X 12']]}
    forms.create_inventory_form.return_value = {'id': 'form', 'publishedUrl': 'respond', 'editUrl': 'edit'}
    service = PdvCreationService(system.master, drive, forms, system.lock, InventoryLock(str(tmp_path/'creation.lock')), system.now, sleep)
    return service, drive, forms, sleep


def test_mass_creation_continues_after_error_and_finishes(system, tmp_path):
    service, drive, forms, sleep = creation(system, tmp_path)
    service.start_mass_creation()
    control = system.sheets.books['master']['Control Formularios']
    rows = {r[0]: r for r in control[1:] if r and r[0]}
    assert rows['bad-xlsx'][2] == 'ERROR'
    assert rows['bad-xlsx'][8] == 'Conversión fallida'
    assert rows['good-xlsx'][2:7] == ['LISTO', 'https://docs.google.com/spreadsheets/d/converted/edit', 'respond', 'edit', 1]
    assert rows['master-xlsx'][8] == 'Formulario inicial'
    assert control[1][11] == 'FINALIZADO'
    assert [c.args[0] for c in sleep.call_args_list] == [60, 3, 60]
    drive.move.assert_called_once_with('form', 'folder')
    assert system.sheets.books['converted']['Configuración'][1] == ['Formulario para responder', 'respond']
    # Reanudar no repite IDs registrados, incluidos ERROR.
    service.start_mass_creation()
    assert drive.convert_xlsx.call_count == 2


def test_adapter_missing_preflight_no_writes(system, tmp_path):
    service, drive, forms, sleep = creation(system, tmp_path)
    forms.adapter.check_configured.side_effect = RuntimeError('Falta adaptador')
    import pytest
    with pytest.raises(RuntimeError, match='Falta adaptador'):
        service.start_mass_creation()
    assert system.sheets.calls == []

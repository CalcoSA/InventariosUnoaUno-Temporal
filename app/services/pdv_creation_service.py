import logging
import time
from app.constants import MIME_XLSX
from app.errors import FunctionalError
from app.utils import remove_xlsx_extension, text, cell

logger = logging.getLogger(__name__)


class PdvCreationService:
    def __init__(self, master, drive, forms, lock, creation_lock, now, sleep=time.sleep):
        self.master, self.drive, self.forms = master, drive, forms
        self.sheets, self.lock, self.creation_lock = master.sheets, lock, creation_lock
        self.now, self.sleep = now, sleep
        self.folder = None
        self.master_name = None

    def start_mass_creation(self):
        self.forms.adapter.check_configured()
        with self.creation_lock.acquire():
            logger.info('Iniciando creación masiva')
            self.folder = self.drive.parent(self.master.book_id)
            self.master_name = remove_xlsx_extension(self.sheets.metadata(self.master.book_id)['properties']['title'])
            with self.lock.acquire():
                self.master.ensure_control()
                self.register_bc01()
                self.sheets.write(self.master.book_id, 'Control Formularios', 1,
                    [['Proceso', 'Creación de formularios'], ['Estado general', 'EN PROCESO'], ['Última revisión', self.now()]], 11)
            logger.info('BC01 registrado/verificado')
            while self.process_next_pdv():
                logger.info('Esperando 60 segundos...')
                self.sleep(60)
            logger.info('Proceso finalizado')

    def register_bc01(self):
        file = next((f for f in self.drive.list_files(self.folder)
            if f['mimeType'] == MIME_XLSX and remove_xlsx_extension(f['name']) == self.master_name), None)
        if not file:
            return
        ids = {text(cell(r, 0)) for r in self.master.control()[1:]}
        if file['id'] in ids:
            return
        book = self.master.book_id
        config = self.sheets.read(book, 'Configuración') if self.sheets.find_sheet(book, 'Configuración') else []
        source = self.sheets.read(book, 'Uno a Uno', display=True) if self.sheets.find_sheet(book, 'Uno a Uno') else None
        self.sheets.append(book, 'Control Formularios', [[file['id'], self.master_name, 'LISTO', f'https://docs.google.com/spreadsheets/d/{book}/edit',
            cell(config[1], 1) if len(config) > 1 else '', cell(config[2], 1) if len(config) > 2 else '',
            len(source) - 1 if source is not None else '', self.now(), 'Formulario inicial']])

    def process_next_pdv(self):
        if not self.folder or self.master_name is None:
            raise FunctionalError('Primero debes ejecutar iniciarCreacionMasiva.')
        book = self.master.book_id
        with self.lock.acquire():
            ids = {text(cell(r, 0)) for r in self.master.control()[1:] if cell(r, 0)}
            pending = next((f for f in self.drive.list_files(self.folder) if f['mimeType'] == MIME_XLSX
                           and remove_xlsx_extension(f['name']) != self.master_name and f['id'] not in ids), None)
            if not pending:
                self.sheets.write(book, 'Control Formularios', 2, [['FINALIZADO'], [self.now()]], 12)
                return False
            name = remove_xlsx_extension(pending['name'])
            row = self.sheets.append(book, 'Control Formularios', [[pending['id'], name, 'PROCESANDO', '', '', '', '', self.now(), '']])
        logger.info('Procesando: %s', name)
        try:
            converted = self.drive.convert_xlsx(pending['id'], name, self.folder)
            self.sleep(3)
            pdv_book = converted['id']
            sheet = self.sheets.find_sheet(pdv_book, 'Uno a Uno', normalized=True, simple=True)
            if not sheet:
                raise FunctionalError('No se encontró la hoja Uno a Uno.')
            source = self.sheets.read(pdv_book, sheet['title'], display=True)
            if len(source) < 2:
                raise FunctionalError('La hoja Uno a Uno no contiene productos.')
            rows = [[cell(r, c) for c in range(4)] for r in source[1:] if cell(r, 1) != '' and cell(r, 2) != '']
            form = self.forms.create_inventory_form(name, rows, pdv_book)
            self.drive.move(form['id'], self.folder)
            self.sheets.ensure_sheet(pdv_book, 'Configuración')
            self.sheets.clear(pdv_book, 'Configuración', all_format=True)
            self.sheets.write(pdv_book, 'Configuración', 1, [['Dato', 'Enlace'], ['Formulario para responder', form['publishedUrl']],
                ['Formulario para editar', form['editUrl']], ['Fecha de creación', self.now()]])
            self.sheets.format_header(pdv_book, 'Configuración', 2, resize=True, color=False)
            with self.lock.acquire():
                self.sheets.write(book, 'Control Formularios', row, [['LISTO', f'https://docs.google.com/spreadsheets/d/{pdv_book}/edit',
                    form['publishedUrl'], form['editUrl'], len(rows), self.now(), '']], 3)
            logger.info('[OK] %s', name)
        except Exception as error:
            logger.exception('%s: %s', name, error)
            with self.lock.acquire():
                self.sheets.write(book, 'Control Formularios', row, [['ERROR']], 3)
                self.sheets.write(book, 'Control Formularios', row, [[self.now(), str(error)]], 8)
        with self.lock.acquire():
            self.sheets.write(book, 'Control Formularios', 3, [[self.now()]], 12)
        return True

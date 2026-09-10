from datetime import datetime
from zoneinfo import ZoneInfo
from app.repositories.master_sheet_repository import MasterSheetRepository
from app.repositories.pdv_sheet_repository import PdvSheetRepository
from app.repositories.general_summary_repository import GeneralSummaryRepository
from app.services.google_auth_service import GoogleAuthService
from app.services.google_sheets_service import GoogleSheetsService
from app.services.google_drive_service import GoogleDriveService
from app.services.google_forms_service import GoogleFormsService
from app.services.forms_compatibility_adapter import FormsCompatibilityAdapter
from app.services.inventory_service import InventoryService
from app.services.inventory_summary_service import InventorySummaryService
from app.services.udm_service import UdmService
from app.services.pdv_creation_service import PdvCreationService
from app.services.locking import InventoryLock


def build_services(config):
    auth = GoogleAuthService(config)
    tz = config['APP_TIMEZONE']
    now = lambda: datetime.now(ZoneInfo(tz))
    sheets = GoogleSheetsService(auth, tz)
    drive = GoogleDriveService(auth)
    forms = GoogleFormsService(auth, FormsCompatibilityAdapter(auth, config['GOOGLE_FORMS_COMPAT_SCRIPT_ID']))
    master = MasterSheetRepository(sheets, config['GOOGLE_MASTER_SPREADSHEET_ID'])
    pdv = PdvSheetRepository(sheets, master)
    general = GeneralSummaryRepository(sheets, config['GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID'])
    lock = InventoryLock(config['INVENTORY_LOCK_PATH'])
    summary = InventorySummaryService(master, pdv, general, lock, now, tz)
    return {'auth': auth, 'sheets': sheets, 'drive': drive, 'forms': forms, 'master': master,
            'inventory': InventoryService(master, pdv, summary, lock, now, tz),
            'summary': summary, 'udm': UdmService(master, pdv, lock, now),
            'creation': PdvCreationService(master, drive, forms, lock, InventoryLock(config['INVENTORY_LOCK_PATH'] + '.creation'), now)}

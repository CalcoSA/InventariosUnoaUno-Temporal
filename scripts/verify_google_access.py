import re
from _bootstrap import application


def verify(app=None):
    app = app or application()
    services = app.extensions['services']
    try:
        services['auth'].credentials(interactive=True)
        print('[OK] Google authentication')
    except Exception as error:
        print(f'[ERROR] Google authentication: {error}')
        return 1
    sheets, drive, master = services['sheets'], services['drive'], services['master']
    errors = []

    def check(label, operation):
        try:
            value = operation()
            print(f'[OK] {label}')
            return value
        except Exception as error:
            errors.append(label)
            print(f'[ERROR] {label}: {error}')

    check('Master spreadsheet', lambda: sheets.metadata(master.book_id))
    control = check('Control Formularios', lambda: master.control(required=True))
    if control:
        print('Encabezados Control Formularios:', control[0][:9])
        print('PDV LISTO (aproximado):', sum(1 for r in control[1:] if len(r) >= 4 and r[1] and r[2].strip().upper() == 'LISTO' and r[3]))
    udm = check('Base de datos UDM', master.read_udm)
    if udm:
        print('Encabezados Base de datos UDM:', udm[0][:5])
    check('General summary spreadsheet', lambda: sheets.metadata(app.config['GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID']))
    check('Master Drive file', lambda: drive.metadata(master.book_id))
    check('Parent Drive folder', lambda: drive.metadata(drive.parent(master.book_id)))
    form_id = None
    for row in control[1:] if control else []:
        if len(row) > 5:
            match = re.search(r'/forms/d/(?!e/)([\w-]+)', row[5])
            if match:
                form_id = match[1]
                break
    if form_id:
        check('Forms API', lambda: services['forms'].get(form_id))
    else:
        print('[SKIP] Forms API: no se encontró URL de edición de Form en Control Formularios; no se crearon formularios de prueba.')
    if not app.config['GOOGLE_FORMS_COMPAT_SCRIPT_ID']:
        print('[INFO] Creación de PDV requiere GOOGLE_FORMS_COMPAT_SCRIPT_ID; consulte compat/README.md.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(verify())

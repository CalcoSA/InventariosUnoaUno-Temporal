import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def application():
    from app import create_app
    return create_app({'DEBUG': False})


def administrative(service, method, description):
    import argparse
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--confirm', action='store_true', help='Ejecutar conscientemente escrituras sobre los documentos Google configurados.')
    args = parser.parse_args()
    if not args.confirm:
        try:
            answer = input(description + '\nEsta operación modifica los documentos Google existentes. Escriba EJECUTAR para continuar: ')
        except EOFError:
            answer = ''
        if answer != 'EJECUTAR':
            print('Cancelado. No se modificaron datos.')
            return 0
    app = application()
    try:
        app.extensions['services']['auth'].credentials(interactive=False)
        result = getattr(app.extensions['services'][service], method)()
        if result:
            print(result)
        return 0
    except Exception as error:
        print(f'[ERROR] {error}')
        return 1

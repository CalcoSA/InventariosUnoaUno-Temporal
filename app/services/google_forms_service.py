import logging
from app.services.google_request import execute
from app.utils import cell

DESCRIPTION = 'Por favor, registre las cantidades físicas encontradas durante el conteo y verifique cuidadosamente la información antes de enviar el formulario.'


class GoogleFormsService:
    def __init__(self, auth, adapter):
        self.auth, self.adapter = auth, adapter

    def api(self):
        return self.auth.api('forms', 'v1').forms()

    def get(self, form_id):
        return execute(self.api().get(formId=form_id))

    def add_products_grouped(self, rows):
        groups = {}
        for row in rows:
            groups.setdefault(cell(row, 0) or 'Productos', []).append(row)
        # Object.keys de Apps Script enumera primero las claves de índice entero.
        def is_index(k):
            return isinstance(k, str) and k.isascii() and k.isdigit() and str(int(k)) == k and int(k) < 4294967295
        keys = sorted((k for k in groups if is_index(k)), key=int) + [k for k in groups if not is_index(k)]
        items = []
        for category in keys:
            items.append({'title': category, 'description': 'Registre la cantidad física encontrada para cada producto.', 'pageBreakItem': {}})
            for row in groups[category]:
                items.append({'title': f'{cell(row, 1)} – {cell(row, 2)}', 'description': f'Unidad de medida: {cell(row, 3)}',
                              'questionItem': {'question': {'required': True, 'textQuestion': {}}}})
        return items

    def create_inventory_form(self, point, rows, spreadsheet_id):
        self.adapter.check_configured()
        form = execute(self.api().create(body={'info': {'title': 'Inventario Uno a Uno – ' + point}}), retry_safe=False)
        form_id = form['formId']
        execute(self.api().batchUpdate(formId=form_id, body={'requests': [
            {'updateFormInfo': {'info': {'description': DESCRIPTION}, 'updateMask': 'description'}}]}))
        try:
            execute(self.api().setPublishSettings(formId=form_id, body={'publishSettings': {'publishState': {'isPublished': True, 'isAcceptingResponses': True}}}))
        except Exception:
            logging.getLogger(__name__).warning('Publicación automática no disponible.', exc_info=True)
        items = [
            {'title': 'Nombre de quien realiza el inventario', 'questionItem': {'question': {'required': True, 'textQuestion': {}}}},
            {'title': 'Fecha del inventario', 'questionItem': {'question': {'required': True, 'dateQuestion': {'includeYear': True, 'includeTime': False}}}},
        ] + self.add_products_grouped(rows)
        # Inserciones no se reintentan tras una respuesta ambigua: podrían duplicar preguntas.
        for start in range(0, len(items), 100):
            requests = [{'createItem': {'item': item, 'location': {'index': i}}} for i, item in enumerate(items[start:start+100], start)]
            execute(self.api().batchUpdate(formId=form_id, body={'requests': requests}), retry_safe=False)
        urls = self.adapter.configure(form_id, spreadsheet_id)
        return {'id': form_id, 'publishedUrl': urls['publishedUrl'], 'editUrl': urls['editUrl']}

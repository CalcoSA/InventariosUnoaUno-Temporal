from app.errors import ConfigurationError, FunctionalError
from app.services.google_request import execute


class FormsCompatibilityAdapter:
    """Únicamente operaciones FormApp sin representación en Forms REST."""
    def __init__(self, auth, script_id):
        self.auth, self.script_id = auth, script_id

    def check_configured(self):
        if not self.script_id:
            raise ConfigurationError('Configure GOOGLE_FORMS_COMPAT_SCRIPT_ID y despliegue compat/forms_adapter.gs como ejecutable de API; Forms REST no permite vincular el destino ni las validaciones numéricas.')

    def call(self, function, parameters, retry_safe=True):
        self.check_configured()
        result = execute(self.auth.api('script', 'v1', timeout=380).scripts().run(
            scriptId=self.script_id, body={'function': function, 'parameters': parameters, 'devMode': False}), retry_safe)
        if 'error' in result:
            detail = result['error'].get('details', [{}])[0]
            raise FunctionalError(detail.get('errorMessage', result['error'].get('message', 'Error del adaptador FormApp.')))
        return result.get('response', {}).get('result')

    def configure(self, form_id, spreadsheet_id):
        return self.call('configurarCompatibilidadInventario', [form_id, spreadsheet_id], retry_safe=False)

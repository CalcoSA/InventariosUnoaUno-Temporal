# Adaptador de compatibilidad de Google Forms

El resto de la aplicación está implementado en Python. Este archivo Apps Script conserva exclusivamente llamadas a FormApp que no tienen representación editable en Forms REST, más la recuperación de las URLs del formulario existente.

| Operación original | Implementación |
|---|---|
| `FormApp.create` | REST `forms.create`, título exacto |
| `setDescription` | REST `forms.batchUpdate` → `updateFormInfo` |
| `setPublished(true)` | REST `forms.setPublishSettings`; fallo no aborta el proceso |
| `addTextItem`, `addDateItem`, `addPageBreakItem`, título, ayuda y obligatorio | REST `createItem`; fecha con año |
| `setConfirmationMessage` | FormApp en el adaptador; no hay campo REST |
| `setProgressBar` | FormApp en el adaptador; no hay campo REST |
| `createTextValidation`, `requireNumberGreaterThanOrEqualTo(0)`, `setValidation` | FormApp en el adaptador; `TextQuestion` REST solo expone `paragraph` |
| `setDestination(SPREADSHEET, id)` | FormApp en el adaptador; `linkedSheetId` REST es solo lectura |
| `getPublishedUrl`, `getEditUrl` | FormApp devuelve ambas URLs en la misma respuesta; REST también expone `responderUri`, pero no una URL de edición |
| Mover el Form a la carpeta | Drive REST `files.update`, desde Python |

Se verificaron tanto la documentación oficial como el discovery incluido en `google-api-python-client` instalado. Fuentes: [recurso Form y sus campos](https://developers.google.com/workspace/forms/api/reference/rest/v1/forms), [batchUpdate](https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate), [publicación](https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/setPublishSettings) y [DateItem de Apps Script](https://developers.google.com/apps-script/reference/forms/date-item).

## Configurar antes de crear PDV

1. En un proyecto Apps Script dedicado a compatibilidad, agregue `forms_adapter.gs` y el manifiesto `appsscript.json` suministrados. Mantenerlo separado evita exigir todos los scopes de otros scripts. También puede agregarse a un proyecto existente, pero en ese caso el cliente OAuth debe solicitar **todos** los scopes del proyecto existente.
2. Vincule Apps Script al **mismo proyecto estándar Google Cloud** donde creó el cliente OAuth de escritorio. Habilite Google Apps Script API en ese proyecto.
3. Despliegue una versión como **Ejecutable de API**, con acceso a la misma cuenta del token. El manifiesto suministrado utiliza `MYSELF`; si cambia el destinatario, configure explícitamente el acceso requerido.
4. Copie el ID del script desde la configuración del proyecto en `.env`: `GOOGLE_FORMS_COMPAT_SCRIPT_ID=...`. Python lo envía como `scriptId` en `scripts.run`; no es la URL `/exec` de una web app.
5. Vuelva a autorizar con `python scripts/verify_google_access.py` después de retirar el token anterior. Al estar configurado el adaptador se incluye el scope `https://www.googleapis.com/auth/forms`, además de Sheets, Drive y Forms body.
6. Ejecute conscientemente `python scripts/create_all_pdv.py` cuando vaya a crear los archivos/formularios de producción.

La API de ejecución requiere despliegue y cliente OAuth en un proyecto Cloud común, todos los scopes y una identidad de usuario; no admite Service Accounts. Referencia: [ejecutar funciones mediante Apps Script API](https://developers.google.com/apps-script/api/how-tos/execute).

El adaptador abre el Form ya creado por REST, aplica la validación a todas las preguntas de texto excepto la primera (nombre), activa progreso, establece el mensaje y vincula el Spreadsheet convertido. Solo recibe dos IDs; no ejecuta cálculos, Sheets, Drive ni el proceso de PDV. Sus errores llegan a Python y se registran como ERROR en Control Formularios. No se reintenta automáticamente una invocación incierta.

No se desplegó ni ejecutó este adaptador durante la construcción. Se requiere verificar el formulario generado con la cuenta y políticas corporativas reales, incluyendo publicación, enlace de respuestas, formato de fecha y configuración predeterminada de Google Forms.

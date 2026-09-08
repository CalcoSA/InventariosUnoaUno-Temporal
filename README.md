# Inventario Uno a Uno — Flask

Primera versión de la migración del Apps Script suministrado. Google Sheets sigue siendo la persistencia; los nombres de PDV proceden de `Control Formularios`. No hay base de datos adicional. La interfaz, CSS y lógica de borradores se conservaron desde `legacy/Index.html`.

La aplicación inicia localmente. Las pruebas usan dobles de Google en memoria y comparaciones con el JavaScript original. **La validación contra los documentos reales está bloqueada por la falta del cliente OAuth `credentials/credentials.json`.** La creación de nuevos Forms requiere además desplegar el adaptador de `compat/`. No se ejecutaron escrituras de producción ni se desplegó a GCP.

## Estructura

```text
app/
  controllers/    Rutas HTTP y errores centralizados
  models/         Producto, conteo y resultado
  services/       OAuth, APIs Google, inventario, resúmenes, UDM y creación PDV
  repositories/   Acceso al maestro, bases PDV y resumen general
  templates/      HTML original adaptado a Flask
  static/css/     CSS original
  static/js/      JavaScript original con fetch
scripts/          Verificación y operaciones administrativas
compat/           Adaptador mínimo FormApp y manifiesto
legacy/           Código fuente vigente suministrado, sin modificar
tests/            Pruebas con mocks y referencia JavaScript
credentials/      JSON privados, excluidos de Git
```

Flujo: Controller → Service → Repository → GoogleSheetsService → API oficial. Drive y Forms están aislados en servicios dedicados. Consulte [MIGRATION_PARITY.md](MIGRATION_PARITY.md) para la correspondencia función por función y [VALIDATION.md](VALIDATION.md) para las verificaciones.

## Ejecutar en este workspace de Windows/VS Code

Se prepararon Python 3.12.10 en `.tools/python/tools/` y un entorno `.venv/` porque `python` no estaba en PATH. No elimine `.tools` mientras utilice ese entorno.

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

Si la política corporativa impide activar scripts, no hace falta cambiarla:

```powershell
.\.venv\Scripts\python.exe run.py
```

Abra http://127.0.0.1:5000. La página carga sin credenciales; las consultas de inventario muestran el mensaje de configuración hasta autorizar Google. El servidor escucha en loopback de forma predeterminada. Ctrl+C lo detiene.

## Instalación desde cero

Instale Python 3.11+ (se verificó con 3.12.10), abra una terminal PowerShell en la raíz del proyecto y ejecute:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

No sobrescriba un `.env` ya configurado. El actual contiene únicamente configuración sin secretos. Para reproducir las versiones verificadas de Windows puede instalar `requirements-lock.txt`.

## Google OAuth: primer paso necesario

**Coloque el JSON de un cliente OAuth 2.0 de tipo “Aplicación de escritorio” en `credentials/credentials.json`.** No use una clave de Service Account.

Para obtenerlo en el proyecto Google Cloud autorizado por su organización: habilite Google Sheets API, Google Drive API y Google Forms API; configure Google Auth Platform (audiencia interna si corresponde, o usuario de prueba permitido); cree el cliente de escritorio y descargue su JSON. Use la cuenta Google que actualmente tiene acceso a los archivos del Apps Script.

Después ejecute:

```powershell
python scripts/verify_google_access.py
```

Se abre el consentimiento OAuth en su navegador mediante un callback de localhost con puerto libre. Al autorizar, se genera `credentials/token.json`, con el refresh token; no lo comparta ni lo agregue a Git. Las ejecuciones posteriores reutilizan y renuevan el token. El servidor web nunca inicia un consentimiento interactivo. Si Google revoca o caduca el refresh token, retire localmente `credentials/token.json` y repita la verificación.

El verificador solo lee: maestro, `Control Formularios`, encabezados UDM, cantidad de PDV LISTO, resumen general, archivo Drive, carpeta padre y un Form existente a partir de su URL de edición. Si no encuentra una URL válida de edición, imprime `[SKIP] Forms API`; eso no equivale a haber validado Forms. Los errores identifican el paso que falló. La creación/renovación del token local es la única escritura del verificador.

Las variables conservan estos documentos exactos:

| Variable | ID |
|---|---|
| `GOOGLE_MASTER_SPREADSHEET_ID` | `1q34wHfO08PDclMA2zSNf03naVkSllG6lCRcHu6dGdg4` |
| `GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID` | `1_Kj9mXyd5q8y1wx6D0sSmbapiGugvxj3yBo437xQk8M` |

`APP_TIMEZONE=America/Bogota` reproduce el huso del script. Si el proyecto Apps Script usa otro huso explícito, configure ese mismo. Los seriales de fecha de Sheets se interpretan con el huso de cada documento, y las claves se forman en el del script.

## Pruebas

```powershell
pytest
```

Node.js solo es necesario para las pruebas diferenciales contra Apps Script y el smoke de JavaScript. No es necesario para ejecutar Flask. Sin Node, esas pruebas se marcan como omitidas. Ninguna prueba utiliza las credenciales reales ni escribe en Google. Los datos de prueba existen únicamente en `tests/`.

## Operaciones administrativas

Estas operaciones **modifican los mismos documentos existentes**. Cada comando pide escribir `EJECUTAR`; `--confirm` permite una ejecución consciente no interactiva. Sin confirmación no escribe.

```powershell
python scripts/create_all_pdv.py
python scripts/update_all_udm.py
python scripts/rebuild_general_summary.py
```

`create_all_pdv.py` requiere [configurar el adaptador FormApp](compat/README.md). Usa la carpeta padre del maestro, registra BC01, convierte cada XLSX en Google, crea el Form, lo mueve a la misma carpeta y actualiza `Configuración` y `Control Formularios`. Procesa un archivo por vez, espera 60 segundos entre ciclos y continúa tras errores. Al terminar marca `FINALIZADO`. Igual que el legacy, los IDs ya registrados con `PROCESANDO` o `ERROR` se consideran procesados: reiniciar el comando no los reprocesa automáticamente. Interrumpirlo puede dejar un PDV en `PROCESANDO`.

`update_all_udm.py` actualiza por nombre de producto normalizado y conserva los valores sin coincidencia; registra los primeros 20 nombres faltantes. `rebuild_general_summary.py` lee primero las bases LISTO, recalcula y luego **limpia el contenido** de `Resumen General` para reescribirlo.

## Google Forms

REST crea el título, descripción, preguntas, secciones y publicación. La API documenta `linkedSheetId` como solo lectura; no ofrece campos para validación numérica de texto, mensaje de confirmación ni barra de progreso. Se conservan esas operaciones en `compat/forms_adapter.gs`, invocado desde Python mediante Apps Script API. No se reemplazan las respuestas por guardados manuales. Consulte [compat/README.md](compat/README.md).

## Concurrencia, fallos y despliegue posterior

`filelock` usa un bloqueo de archivo del sistema operativo con espera máxima de 30 segundos. Todos los procesos de la aplicación y scripts deben compartir la ruta absoluta `INVENTORY_LOCK_PATH`. El guardado mantiene el bloqueo desde la revisión del destino/duplicado hasta terminar ambos resúmenes. La creación masiva tiene además un bloqueo de ejecución para impedir dos ciclos simultáneos.

**Una única instancia/servidor con filesystem común.** Contenedores con discos separados no comparten el lock. Apps Script original tampoco participa en ese bloqueo: no opere simultáneamente los dos sistemas para escribir inventarios. El Dockerfile deja Gunicorn con un worker y ocho hilos; montar credenciales y configuración externamente. No incluye secretos en la imagen, y ejecuta sin root con debug desactivado. No se ha construido ni desplegado la imagen en esta máquina.

Sheets no proporciona una transacción que abarque varios documentos. Igual que en el legacy, si el conteo se escribe y después falla un resumen, el conteo permanece; un reintento del envío puede ser rechazado como duplicado. Revise los logs antes de intervenir. El borrador se conserva cuando la respuesta HTTP es un error. La reconstrucción general permite reparar ese resumen; no se agregó una operación de recuperación funcional nueva.

Las lecturas y escrituras idempotentes a rangos fijos tienen hasta tres reintentos con backoff para 429/500/502/503/504. Creación de archivos, inserción de preguntas y ejecución del adaptador no se repiten automáticamente tras errores ambiguos para evitar duplicados; el PDV queda registrado como ERROR. Los artefactos parciales se conservan, como en Apps Script.

El frontend no recibe trazas. Se validan cantidades en backend y se recalculan factor y físico; se rechazan cantidades no finitas además de negativas/no numéricas porque Google no puede persistir Infinity como número JSON. Los headers HTTP y el límite de 8 MiB no modifican la pantalla. El control de acceso de producción debe mantenerse dentro del entorno corporativo; este trabajo no despliega un sitio público.

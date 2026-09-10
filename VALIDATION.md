# Verificaciones de la revisión final

## Docker Compose, CI/CD y WordPress (10 de septiembre de 2026)

Se sustituyó la preparación anterior por `Dockerfile`, `compose.yaml` y el workflow automático de GitHub Actions. Se eliminó `deploy/` y se trasladó el PHP a `wordpress/inventarios-sso.php`, compatible con Woody o como plugin independiente. Las instrucciones vigentes están en [GitHub](docs/GITHUB_ACTIONS.md), [GCP](docs/GCP_DOCKER.md) y [WordPress](docs/WORDPRESS_SSO.md).

**198 casos aprobados:** primera ejecución completa `190 passed, 8 skipped` por ausencia de PHP; después se ejecutaron los ocho casos omitidos con PHP portable 8.4.25 y OpenSSL: `8 passed`. No quedan casos pendientes de esa suite. Los diez casos de despliegue usan comandos simulados y comprueban instalación inicial, orden de parada/arranque, fallos de carga/configuración, rechazo de otra etiqueta, recuperación y fallo de recuperación. No acceden a una VM ni a Docker real.

| Comprobación | Resultado |
|---|---|
| Workflow | `actionlint` 1.7.12, sin errores; sin analizadores externos shellcheck/pyflakes |
| Compose | CLI oficial 5.5.1, `config --quiet --no-env-resolution --no-path-resolution`, sin errores |
| Ejecutor remoto | `bash -n` y diez pruebas simuladas aprobadas |
| WordPress | `php -n -l` sin errores y ocho pruebas reales PHP/OpenSSL ↔ Flask aprobadas |
| JavaScript | `node --check` de autenticación e inventario aprobado |
| Documentación | Enlaces locales vigentes; instrucciones antiguas redirigidas a Docker |

Los validadores portables se descargaron desde sus proveedores oficiales, se verificaron por SHA-256 y se retiraron al terminar. **No se construyó ni arrancó un contenedor local:** no hay Docker Engine disponible en este entorno. El workflow realiza build, `pip check` y comprobación con test client dentro de la imagen antes de desplegar; el ejecutor en GCP verifica configuración real y espera a que el contenedor esté saludable. Esas ejecuciones de infraestructura quedan pendientes de configurar la VM y GitHub. No se inició ningún servidor local ni se escribió en Google, GCP o WordPress. `.env` y la lógica de inventario permanecen intactos.

## Fase posterior: SSO, inactividad y preparación Apache (9 de septiembre de 2026)

Suite final: **188 passed**, sin omisiones, frente a las 82 pruebas anteriores (**106 casos añadidos**). Ejecutada con Python 3.12.10, Node 24.19.0, PyJWT 2.13.0 y PHP portátil 8.4.25 con OpenSSL. El PHP de validación se descargó del proveedor oficial, se verificó su SHA256 y se retiró después; para repetir sus ocho casos en otra máquina instalar PHP CLI o indicar `PHP_TEST_BINARY`. Sin PHP esos ocho casos se omiten; sin Node se omiten las pruebas JavaScript según la configuración existente.

Comando ejecutado, con `PHP_TEST_BINARY` apuntando temporalmente al PHP de validación:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

| Verificación nueva | Resultado |
|---|---|
| `tests/test_sso.py` y `tests/auth_frontend.cjs` | RS256 válido, firma/algoritmo/claims inválidos, replay concurrente/TTL, cookies, CSRF, rutas protegidas, configuración de producción, sesión HS256, proxy limitado, no exposición de JWT |
| Reloj simulado servidor | Actividad a intervalos extiende más de 20 min desde login; exactamente 1200 s sin actividad rechaza; un heartbeat retrasado descuenta la demora; sesión vencida no se renueva |
| Reloj simulado de dos pestañas | La pestaña activa mantiene la sesión compartida, incluso con storage deshabilitado; la inactiva no elimina cookies; cierre tras inactividad de ambas |
| Borrador | Expiración, 401 y logout conservan la clave y contenido; la función real `recuperarBorrador()` recupera Cerrado/Abierto |
| `tests/test_woody.py` + `tests/woody_harness.php` | 8 casos: PHP real/OpenSSL firma un JWT que Flask acepta; replay rechazado; botón en pestaña nueva; login/nonce/método/clave/subject inválidos fallan de forma segura |
| Sintaxis PHP | `php -n -l wordpress/inventarios-sso.php`: sin errores |
| `pip check` | Sin dependencias rotas |
| Sintaxis JavaScript | `node --check` correcto para auth.js e inventory.js |
| Entrada WSGI | `wsgi:app` importable y healthcheck 200 mediante test client, sin Google ni puerto |
| Cargador de Gunicorn 23 | `gunicorn.util.import_app('wsgi:app')` correcto en Windows; solo se suministraron módulos POSIX vacíos que fallan ante cualquier uso para poder importar el cargador. No se emuló ni arrancó un worker. `--check-config` y ejecución POSIX reales quedan indicados en la guía Debian |
| Paridad funcional | Las 82 pruebas previas pasan, incluido cuerpo HTML/CSS, borradores y comparación con legacy; inventory.js, servicios de negocio, repositorios, modelos y scripts permanecen intactos |
| Google Forms compat | Discovery instalado y referencia oficial exigen Deployment ID del ejecutable API pese al nombre `scriptId`; se corrigió la documentación, sin modificar el adaptador |
| OAuth local | Solo se comprobaron presencia del ID compat y pertenencia del scope; ID vacío y scope completo Forms ausente. No se imprimió, borró, refrescó ni regeneró el token |
| Despliegue/infraestructura | Solo plantillas y guía; ningún cambio en WordPress, Apache, GCP, DNS, certificados o Apps Script |

Estas pruebas no llaman Google real: el fixture bloquea el proveedor de API. Los POST de inventario usan hojas en RAM. En esta fase no se ejecutó ninguna verificación Google por red ni ningún comando administrativo de escritura. No se inició `run.py`, Flask, Gunicorn ni PHP como servidor. La aceptación real del SSO WordPress/Apache y el arranque en Debian siguen siendo pasos manuales, no resultados locales inferidos.

Cierre local: eliminados **seis directorios temporales** (PHP portátil y su ZIP dentro de `.runtime/php-validation`, más cinco `__pycache__` propios de app). Se conservaron `.venv`, `.tools/python`, credenciales, legacy, compat, tests y documentos. Inspección final de procesos: ningún Python/PHP/Gunicorn; **ningún listener en 5000 u 8000**. No se detuvo ningún proceso ajeno. No había archivos Nginx obsoletos para retirar. `.gitignore` y `.dockerignore` excluyen también claves PEM/KEY y JSON privados.

Archivos de operación: [GCP y Docker](docs/GCP_DOCKER.md), [GitHub y Secrets](docs/GITHUB_ACTIONS.md), [WordPress](docs/WORDPRESS_SSO.md), [AUTENTICACION_SSO.md](docs/AUTENTICACION_SSO.md), [PHP SSO](wordpress/inventarios-sso.php) y [Compose](compose.yaml).

## Evidencia histórica de lectura Google anterior a la fase SSO

Fecha: 9 de septiembre de 2026. Entorno: Windows, Python 3.12.10 del proyecto y Node.js 24.19.0. Se revisó el código actual; no se modificó la implementación funcional.

| Verificación | Resultado y alcance |
|---|---|
| `python -m pytest -q` | **82 passed**, sin pruebas omitidas |
| `python -m pip check` | `No broken requirements found.` |
| `node --check app/static/js/inventory.js` | Correcto |
| Servidor anterior del agente | Detenido; puerto 5000 libre; sin procesos Python del proyecto tras terminar |
| Servidor iniciado para esta revisión | Ninguno: se utilizó `app.test_client()` |
| GET `/` | HTTP 200 mediante test client |
| GET `/api/puntos-venta` con Google real | HTTP 200, **35 nombres de PDV** |
| GET `/api/productos?pdv=...` con Google real | HTTP 200 para **35 de 35 PDV**, **5580 filas de producto** entre todas sus bases; no son productos únicos globales |
| Factores de los productos devueltos | Todos numéricos y positivos; no se guardaron conteos |
| GET `/api/categorias` de BC01 - Cocina Envigado | HTTP 200, 8 categorías |
| GET `/api/productos` de BC01, categoría Bebidas | HTTP 200, 21 productos; mismos resultados que filtrar la lista completa |
| Maestro, Control Formularios y UDM | Lecturas correctas; encabezados comprobados |
| Drive del maestro y carpeta padre | Lecturas correctas |
| Documento general | Accesible; contiene la hoja `Resumen General`; no se limpió ni escribió |
| Form existente tomado de Control Formularios | Lectura correcta: 169 items y destino de Spreadsheet vinculado presente |
| Adaptador FormApp | Fuente incluida; `GOOGLE_FORMS_COMPAT_SCRIPT_ID` vacío; ejecución no probada |
| Solicitudes de la auditoría a Sheets/Drive/Forms | **196 GET**; la auditoría rechazaba métodos de escritura antes de ejecutarlos |
| Escrituras Google en esta revisión | **Ninguna** |
| HTML/CSS respecto al legacy | Cuerpo HTML y CSS idénticos según prueba automática |
| Flujo JavaScript | DOM/fetch simulados: selección, carga, búsqueda, borrador, recuperación, progreso, completar, error, éxito y reinicio |
| Guardado, resúmenes, UDM y creación PDV | Pruebas con mocks; sin aceptación de escrituras reales en esta revisión |
| Comparación con Apps Script original | Utilidades, orden español y flujos de guardado, reconstrucción y UDM sobre hojas simuladas |
| Concurrencia | Dos envíos simulados: solo uno aceptado; bloqueo comprobado entre procesos |
| Error de red | Prueba verifica traceback en servidor y mensaje genérico en frontend |
| Schemas Google | Pruebas contra discovery oficial instalado para Forms, Sheets y conversión Drive |
| Navegador real / revisión visual | No se hizo una nueva inspección visual; no se deduce de la prueba de DOM |
| Docker / GCP | Dockerfile inspeccionado; no se construyó imagen ni se desplegó |

Categorías reales de la muestra BC01: Bebidas, Bodega, Café, Cocina, Dulces, Empaques, Postres Y Helados y Pulpas.

Encabezados del maestro leídos:

- Control Formularios: ID archivo, Punto de venta, Estado, Base Google Sheets, Formulario para responder, Formulario para editar, Productos, Fecha, Detalle.
- Base de datos UDM: Referencia, Desc. item, Desc. U.M., Factor U.M., U.M.

## Alcance de la comparación

Las pruebas bloquean conexiones Google de la aplicación mediante un fixture y manipulan hojas simuladas en RAM. Los casos diferenciales ejecutan los archivos de `legacy/` con Node y comparan su salida con Python. UUID y fechas de ejecución se sustituyen por marcadores solo durante la comparación. Las lecturas reales se hicieron separadamente con el test client y las credenciales existentes.

La evidencia de la auditoría queda resumida en este documento. Sus archivos puntuales `.runtime/final_review_readonly.json` y `.runtime/final_review_readonly.py` se retiraron durante la limpieza posterior; no eran componentes de ejecución ni pruebas permanentes. La renovación normal de un token OAuth, si corresponde, solo actualiza el archivo local de token; no es una escritura en Sheets/Drive/Forms.

No se ejecutaron `POST /api/inventarios` real, create_all_pdv, update_all_udm ni rebuild_general_summary. Los POST de la suite usan mocks. No se creó ningún Form ni se modificó, limpió o eliminó un documento de Google.

## Lo que estas comprobaciones no certifican

La ampliación documental del mismo día hizo **4 GET adicionales de Sheets**: Control Formularios (metadatos y datos), metadatos BC01/maestro y metadatos del general. Confirmó 35 filas LISTO (2–36), 35 IDs distintos y BC01 en fila 2 con base igual al maestro. Las cuatro pestañas solicitadas de BC01 existen. No leyó contenidos de conteos, no inició servidor ni ejecutó POST o comandos administrativos. Las URLs exactas D/E/F y todos los títulos de pestaña quedaron en [docs/FUNCIONAMIENTO_SISTEMA.md](docs/FUNCIONAMIENTO_SISTEMA.md). Su JSON auxiliar también se retiró tras verificar el mapa. Las **82 pruebas** de la tabla corresponden a la revisión previa; no se volvió a ejecutar la suite completa en esta ampliación.

Cierre de la ampliación: comparación automática de las 35 filas documentadas contra D/E/F e IDs leídos, enlaces locales existentes y Markdown sin marcadores pendientes. `python -B -m pytest tests/test_documentation.py -q -p no:cacheprovider`: **1 passed**; esta prueba solo comprueba la matriz documental, no realiza POST. Consulta de procesos: **0 procesos Python del proyecto, 0 listeners en 5000**. Se eliminaron tres diagnósticos puntuales, el ZIP instalador, `.pytest_cache` y ocho directorios `__pycache__` propios; `.runtime/`, `.venv/` y el Python extraído se conservaron. Git no tiene cachés/diagnósticos/logs versionados y no hay cambios en `app/`, `scripts/`, `legacy/` ni `run.py`.

No equivalen a paridad integral en producción. Aún se requiere aceptación controlada del guardado real y sus resúmenes, operaciones administrativas de escritura, creación completa de PDV/Form con el adaptador y posibles funciones/triggers de proyectos remotos cuya fuente no fue suministrada. La lista de los 35 PDV y sus productos sí fue leída con éxito.

El detalle funcional y el dictamen de retiro de Apps Script están en [FINAL_REVIEW.md](FINAL_REVIEW.md). La correspondencia de funciones está en [MIGRATION_PARITY.md](MIGRATION_PARITY.md). No se recomienda regenerar las credenciales que ya funcionan; la configuración pendiente identificada es la del adaptador para crear PDV.

# Concurrencia y solicitudes a Google Sheets

Revisión del 17 de septiembre de 2026. Cambios locales, sin commit, push ni despliegue.

Nota posterior: las cifras de guardado de este documento son históricas. La
optimización y validación posterior de 36/40 guardados está en
[CONCURRENCIA_GUARDADO.md](../CONCURRENCIA_GUARDADO.md); las mejoras de lectura se conservaron.

## Diagnóstico y comprobación pública

El texto de la foto está asociado exclusivamente a `HttpError` con estado 429 en
`app/controllers/error_controller.py`. No es el mensaje genérico de errores de red
ni el de permisos 403. Esto relaciona el síntoma con 429, pero no identifica la cuota
concreta agotada: no se consultaron logs ni métricas privadas de producción.

Se realizaron tres GET de baja carga, sin credenciales ni redirecciones:

- `/healthz`: 200, `{"status":"ok"}`.
- `/`: 401, página de acceso.
- `/api/puntos-venta`: 401, sesión expirada.

El SSO impidió consultar los flujos internos. No se intentó evadirlo. La reproducción
de concurrencia y errores de Google usa únicamente mocks, hojas en memoria y Flask
test client. No se ejecutó `POST /api/inventarios` en producción, ningún script
administrativo ni ninguna escritura real en Sheets, Drive o Forms.

El cuello de botella identificado en el código son las lecturas repetidas: cada
consulta de categorías y productos volvía a obtener metadatos y Control Formularios,
metadatos del PDV y dos veces Uno a Uno. Todos los usuarios repetían estas lecturas.
GoogleAuthService ya crea transportes independientes por llamada y protege la carga
de credenciales; se conservó. También se conservaron el bloqueo del guardado, la
autenticación, el frontend, localStorage y todas las reglas de inventario.

## Llamadas por flujo

Conteos de solicitudes REST ejecutadas, sin reintentos, OAuth ni archivos estáticos.
Medidos en un transporte simulado que cuenta `request.execute(num_retries=0)` del
GoogleSheetsService real; el código original se cargó desde HEAD en memoria para
comparar, sin restaurar ni modificar el working tree.

La columna posterior corresponde al flujo consecutivo dentro de los TTL, empezando
con caché vacía; todas las hojas existen y el catálogo contiene productos.

| Acción | Antes | Después | Consultas posteriores con caché vigente |
|---|---:|---:|---:|
| Abrir aplicación: lista de PDV | 2 | 2 | 0 |
| Seleccionar PDV: categorías | 5 | 2 | 0 |
| Seleccionar categoría en el selector | 0 | 0 | 0 |
| Comenzar inventario: productos | 5 | 0 | 0 |
| Total de consultas antes del guardado | 12 | 4 | 0 |
| Guardar inventario, escenario descrito abajo | 37 | 35 | 35 |

Una consulta directa de categorías/productos con ambas cachés vacías cuesta 4
solicitudes: dos del maestro y dos del catálogo. Al vencer únicamente la lista PDV
cuesta 2; al vencer únicamente el catálogo cuesta 2. No se sirve contenido vencido.

El guardado medido usa hojas existentes, capacidad suficiente, conteos previos de
otra fecha y adición de un grupo nuevo al Resumen General, sin dividir el batch.
Antes: 28 GET + 8 batchUpdate + 1 clear; después: 26 GET + 8 batchUpdate + 1 clear.
La reducción proviene de omitir la lectura de factores que el resumen no utiliza
cuando Conteos Inventarios ya contiene su columna Factor. Si esa columna falta,
se mantiene la lectura de factores original. Crear hojas, ampliar grillas, mezclar
actualizaciones con adiciones y reintentar errores puede aumentar estas cifras.

## Caché, concurrencia y consistencia

- Control Formularios: TTL de 45 segundos, una entrada por repositorio maestro.
  Solo las consultas de pantalla optan por usarla.
- Productos: TTL de 180 segundos, máximo de 64 bases, expulsión de la menos usada.
  Clave por ID de Spreadsheet, sin mezclar bases de PDV distintos. Categorías y
  factores mostrados se derivan de este mismo catálogo, conservando la lógica previa.
- `ReadCache` usa reloj monotónico, lock corto y una Future por carga pendiente.
  Los solicitantes del mismo recurso comparten resultado o error; bases diferentes
  pueden cargar simultáneamente. Los fallos no se almacenan. Cada consumidor recibe
  una copia para no alterar el contenido compartido.
- Todo vive en RAM del proceso; sin Redis, base de datos, archivos ni dependencias
  nuevas. La caché se pierde al reiniciar y no se comparte entre procesos.
- El guardado obtiene Control Formularios y factores frescos; duplicados y conteos
  se leen directamente bajo el InventoryLock existente. No se cachean conteos,
  resúmenes, resultado del guardado ni validación de duplicados. Se conservó el lock
  global porque también protege el Resumen General compartido entre PDV.

Los cambios externos de catálogo pueden tardar hasta 3 minutos en verse en pantalla
y los de la lista PDV hasta 45 segundos. Sheets sigue siendo la fuente de verdad.
La fórmula, la clave Fecha + PDV + Categoría y el orden del guardado no cambiaron.

## Lecturas agrupadas y HTTP 429

`read_views` obtiene valores visibles y tipados de un mismo `spreadsheets.get` con
grid data. Se preservan formatos, ceros iniciales, fechas y fórmulas vacías; no se
sustituyó por values.batchGet para evitar cambiar esa semántica. Las escrituras ya
agrupaban rangos con spreadsheets.batchUpdate; se conservaron sin ampliar retries
ni agrupar las etapas críticas del guardado.

La política de retries ya era adecuada y no se modificó: 429, 500, 502, 503 y 504;
máximo 4 intentos, esperas de 1, 2 y 4 segundos más jitter aleatorio [0, 1).
Las operaciones marcadas no idempotentes no se reintentan. Un 403 no se convierte
en 429. Al agotar los intentos se mantiene el mensaje controlado existente y su
respuesta HTTP 502; no se exponen detalles de Google ni traceback al usuario.
La mejora frente al 429 consiste en reducir solicitudes repetidas y compartir las
cargas concurrentes, incluyendo su ciclo de reintentos, sin cachear errores.

## Pruebas y límites

Pruebas añadidas: `tests/test_read_cache.py`, `tests/test_inventory_concurrency.py`
y casos en `tests/test_google_services.py`; el fake existente incorpora read_views.

- Carga simulada de 10/20/40 usuarios, cada uno consultando PDV, categorías y
  productos: 4 solicitudes Google totales por escenario, frente a 120/240/480 antes.
  Solo una lee Control Formularios y una lee Uno a Uno; las otras dos son metadatos.
- 20 threads retenidos durante una carga: 1 llamada al backend y 20 resultados;
  también comparten un fallo y pueden recuperarse en la siguiente solicitud.
- Vencimiento exacto, copias independientes, capacidad limitada, separación por
  base y cargas paralelas de claves diferentes.
- 429 → 429 → éxito: esperas simuladas crecientes con jitter; cuatro 429 consecutivos:
  mensaje controlado y siguiente solicitud capaz de recuperarse. Sin esperas reales.
- 20 guardados sobre hojas simuladas: uno aceptado, 19 duplicados rechazados;
  factor, Conteo Físico y ambos resúmenes correctos. Ningún guardado en Google real.
- Factores y disponibilidad del PDV cambiados después de calentar la caché siguen
  revalidándose al guardar; se conserva el fallback de factores en conteos antiguos.

Ejecutar primero las pruebas específicas:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_read_cache.py tests/test_inventory_concurrency.py tests/test_google_services.py tests/test_inventory_calculation.py tests/test_summaries.py tests/test_duplicate_key.py tests/test_factors.py tests/test_google_discovery_contract.py -q -p no:cacheprovider
```

Después, la suite completa y la comprobación de dependencias existente:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -rs
.\.venv\Scripts\python.exe -B -m pip check
```

Resultados finales: 16 casos añadidos; 62 pruebas específicas aprobadas. Suite
completa: **204 aprobadas, 2 fallidas y 8 omitidas**. Las omisiones son los tests
opcionales de PHP/OpenSSL, porque PHP CLI no está instalado. `pip check` terminó
con `No broken requirements found.`

Los dos fallos se reprodujeron cargando las versiones originales de los cinco
archivos backend modificados directamente desde HEAD en un proceso aislado, sin
alterar el working tree:

- `tests/test_sso.py::test_production_rejects_bad_config[changes0]`: la configuración
  de producción con AUTH_ENABLED=False no lanza el ValueError esperado.
- `tests/test_sso.py::test_proxy_trusts_one_local_hop_only`: se acepta el Host
  reenviado donde la prueba espera conservar el Host original.

Son fallos preexistentes ajenos a estos cambios. No se tocaron SSO, JWT, proxy ni
configuración de producción, conforme a las restricciones de la tarea. Por tanto,
la suite completa no está verde y no se afirma que lo esté.

No se inició run.py ni ningún servidor local. Estas simulaciones demuestran la
reducción de solicitudes y la preservación de reglas; no certifican capacidad real
ni ausencia de futuros 429 en producción. Las escrituras siguen consumiendo cuota.

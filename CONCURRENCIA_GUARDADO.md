# Guardados simultáneos — 17 de septiembre de 2026

**Se redujo de 35 a 10 llamadas por guardado. Las pruebas locales de 36 y 40
guardados distintos finalizaron, pero NO certifican ausencia de 429 en producción.**
Se usaron Flask test client, InventoryLock y GoogleSheetsService reales, con un
transporte Google simulado en RAM. Sin servidores, Google real ni despliegue.

## Antes y después: un guardado

Ruta: `POST /api/inventarios` → controller → InventoryService → repositorios →
GoogleSheetsService → google_request.execute. Conteo REST con hojas existentes,
capacidad suficiente y sin reintentos:

| Operación | Antes | Después |
|---|---:|---:|
| Buscar base del PDV: metadatos + Control Formularios | 2 | 2 |
| Ubicar Uno a Uno y leer factores | 2 | 2 |
| Preparar Conteos: verificar hoja, encabezado y formato | 5 | 0¹ |
| Leer estado fresco para duplicados | 2 | 2 |
| Agregar conteos, formato de fecha y autoResize | 6 | 1¹ |
| Volver a leer conteos para Resumen Inventario | 2 | 0² |
| Limpiar/escribir/formatear Resumen Inventario | 7 | 0¹ |
| Preparar y leer Resumen General | 3 | 2 |
| Actualizar/agregar filas del General | 4 | 1³ |
| Formato y autoResize del General | 2 | 0³ |
| **Total** | **35** | **10** |

¹ Un batch del PDV incluye conteos y reemplazo del resumen, en ese orden.
² Se reutiliza la lectura fresca bajo lock más las filas del envío, sin caché TTL.
³ Un batch del General agrupa actualizaciones, adiciones, grilla, fechas y autoResize.
Antes: 26 GET + 8 batchUpdate + 1 clear; después: 8 GET + 2 batchUpdate.
Crear hojas, no encontrar el catálogo y reintentar errores cambia estas cifras.

## Cuello de botella y bloqueo

Las llamadas repetidas dentro del lock global bajaron de 31 a 6. Antes, un guardado
retuvo el lock 3,14 s y 36 usuarios produjeron 26 timeouts. Se mantuvo el lock global:
también protege el General y coordina las operaciones administrativas existentes.

El timeout del guardado pasó de **30 a 60 s en código**; otros usos conservan 30 s.
Primero se optimizó: con batches y 30 s terminaron las tandas pequeñas, pero con
40 productos por inventario aparecieron rechazos. La validación final observó
31,06 s de espera, o 32,40 s con dos 429 transitorios. Los 60 s dan margen para ese
perfil; los timeouts HTTP del servidor siguen intactos y no fueron validados.

Se conservaron fórmula y claves del legacy, factores frescos y las mejoras de
lectura previas. El PDV se reconstruye completo usando el primer factor del grupo;
el General suma los físicos individuales. Se aplican encabezados al crear/reparar
y congelación si falta. AutoResize sigue en los batches para conservar anchos;
no hay llamadas separadas de formato ni escrituras por producto.

## Mediciones de carga

Tandas simultáneas con PDV/categorías distintos, hojas con encabezados sin histórico
y **100 ms artificiales por llamada**, sin cuota ni fallos inyectados. Son tiempos
locales de pared en segundos, no mediciones de producción. Fallos aquí = timeout.

Comparación con **un producto por inventario**; las tandas posteriores de esta tabla
ya finalizaron con timeout de 30 s, antes del ajuste final a 60 s:

| Usuarios | Éxitos antes/después | Fallos antes/después | Total antes/después | Máx. espera antes/después | Llamadas antes/después |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 / 1 | 0 / 0 | 3,567 / 1,035 | 0,002 / 0,003 | 35 / 10 |
| 5 | 5 / 5 | 0 / 0 | 16,263 / 3,638 | 12,673 / 2,615 | 175 / 50 |
| 10 | 10 / 10 | 0 / 0 | 32,162 / 6,832 | 28,580 / 5,791 | 350 / 100 |
| 20 | 10 / 20 | 10 / 0 | 31,952 / 13,030 | 30,051 / 11,974 | 390 / 200 |
| 36 | 10 / 36 | 26 / 0 | 32,006 / 23,049 | 30,063 / 21,888 | 454 / 360 |
| 40 | 10 / 40 | 30 / 0 | 31,995 / 25,645 | 30,055 / 24,554 | 470 / 400 |

Validación final ampliada: **40 productos por inventario, timeout de 60 s**:

| Usuarios | Éxitos | Fallos / timeouts / duplicados / 429 | Total | Máx. solicitud | Máx. espera | Llamadas |
|---:|---:|---|---:|---:|---:|---:|
| 36 | 36 | 0 / 0 / 0 / 0 | 28,260 | 28,203 | 26,857 | 360 |
| 40 | 40 | 0 / 0 / 0 / 0 | 32,455 | 32,440 | 31,064 | 400 |

Se verificaron 1.440/1.600 filas, UUID, factores y ambos resúmenes, sin pérdida ni
duplicación. También terminaron 36 categorías de un mismo PDV. De 36 envíos del
mismo duplicado se aceptó uno y se rechazaron 35, sin repetir escrituras.

## Retries y límites que permanecen

Se mantienen 4 intentos para 429/500/502/503/504: 1/2/4 s más jitter. Se repiten UUID,
valores y rangos fijos bajo lock, sin recalcular sumas ni usar append. Un 503 tras
aplicar la escritura no duplicó datos. Los batches con creación NO se reintentan.
Al agotarse los intentos se devuelve un mensaje controlado, sin anunciar éxito.

Con **dos 429 y esperas reales**, 36 guardados de 40 productos terminaron en
**34,222 s**, espera máxima 32,401 s, 362 llamadas y cero fallos/timeouts.
Otra prueba recuperó 74 errores 429 en 36 guardados (434 llamadas), con esperas
mockeadas: valida lógica e integridad, no duración de 74 backoffs.

**Cuota:** Google publica 60 lecturas y 60 escrituras/minuto por usuario/proyecto.
36 guardados aún requieren 288 lecturas y 72 escrituras; con OAuth compartido y
esas cuotas, el lote no cabe en una ventana. No se consultaron cuotas reales.
Simulando esa ventana fija sin reposición, terminaron 7 de 36 envíos consecutivos;
29 recibieron errores controlados. Los retries no resuelven una cuota persistente.
[Fuente oficial](https://developers.google.com/workspace/sheets/api/limits).

**Transacción:** el batch PDV es atómico, pero PDV y General son libros distintos.
Se comprobó que un fallo definitivo del General deja conteos/resumen PDV guardados
y el General pendiente: no se responde éxito ni se duplican conteos al reenviar;
requiere conciliación posterior. Esta limitación entre libros ya existía.
[Atomicidad de batches](https://developers.google.com/workspace/sheets/api/guides/batch).
Historiales, latencia, cuota y límites HTTP impiden garantizar producción sin fallos.

## Reproducción y regresión

`tests/tools/save_load.py` imprime duraciones individuales, total, esperas, llamadas,
éxitos, timeouts, duplicados y 429; `tests/fake_google_transport.py` simula Google.

```powershell
.\.venv\Scripts\python.exe -B tests/tools/save_load.py --latency 0.1
.\.venv\Scripts\python.exe -B tests/tools/save_load.py --latency 0.1 --users 36 40 --products 40
.\.venv\Scripts\python.exe -B tests/tools/save_load.py --latency 0.1 --users 36 --products 40 --initial-429 2
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -rs
```

Se añadieron 19 casos. Pasaron **76 pruebas específicas** (legacy, schemas, creación,
grillas, resúmenes, duplicados, locks y fallos). Suite: **223 aprobadas, 2 fallos
preexistentes de SSO/proxy y 8 omitidas por falta de PHP**.
Los fallos son `test_production_rejects_bad_config[changes0]` y
`test_proxy_trusts_one_local_hop_only`, ya verificados contra HEAD en la tarea previa.
Sin cambios de autenticación, Docker/env/deploy/CI ni pruebas de esos fallos.
Sin escrituras Google, commit ni push. El working tree conserva los cambios previos.

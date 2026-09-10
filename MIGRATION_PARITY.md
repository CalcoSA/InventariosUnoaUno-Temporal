# Paridad de migración

Fase SSO posterior: las reglas y el cuerpo visual del inventario conservan su paridad; se añadió exclusivamente protección HTTP y un script independiente de inactividad en el head de la página. Las **188 pruebas** de [VALIDATION.md](VALIDATION.md) incluyen las 82 previas y 106 casos de seguridad/integración. La creación de PDV conserva el adaptador; su variable SCRIPT_ID requiere el Deployment ID del ejecutable API, como se aclara en [compat/README.md](compat/README.md).

Fuente funcional: `legacy/CrearTodosPDV.gs`, `legacy/Codigo.gs` vigente y `legacy/Index.html`, extraídos íntegramente del adjunto. No se utilizó la versión antigua de diez columnas. La verificación local no equivale a aceptación sobre Google real.

Actualización del 9 de septiembre de 2026: OAuth y las lecturas reales funcionan; se recuperaron los productos de los 35 PDV. El antiguo bloqueo por ausencia de credenciales ya no aplica. El adaptador no está configurado localmente (`GOOGLE_FORMS_COMPAT_SCRIPT_ID` vacío).

Estados: **OK** = implementación y comportamiento verificados dentro del alcance indicado en observaciones y [VALIDATION.md](VALIDATION.md); no implica que todas las escrituras se hayan probado en producción. **BLOCKED_BY_CREDENTIALS** queda reservado para un fallo de acceso, que no se observó en esta revisión. **COMPATIBILITY_ADAPTER** = el flujo requiere el adaptador FormApp incluido y su configuración/aceptación real sigue pendiente. Esta revisión no ejecutó escrituras en Google.

La ubicación de los datos, distinción entre respuestas de Forms y Conteos, y condiciones para retirar cada script están en [FINAL_REVIEW.md](FINAL_REVIEW.md). La matriz se limita a las copias fuente presentes en `legacy/`; no acredita código o triggers remotos no suministrados.

| Función original | Implementación Python | Estado | Observaciones |
|---|---|---|---|
| `iniciarCreacionMasiva` | `PdvCreationService.start_mass_creation` | COMPATIBILITY_ADAPTER | Carpeta padre, BC01, K1:L3, lock exclusivo y ciclo secuencial. También requiere el adaptador. |
| `procesarSiguientePDV` | `PdvCreationService.process_next_pdv` | COMPATIBILITY_ADAPTER | Primer XLSX no registrado, 3 segundos tras conversión, estados y continuación tras ERROR; pausa de 60 segundos. |
| `agregarProductosMasivo_` | `GoogleFormsService.add_products_grouped` + adaptador | COMPATIBILITY_ADAPTER | Categorías, orden de Object.keys, secciones, texto exacto, pregunta requerida y validación >= 0. |
| `registrarBC01_` | `PdvCreationService.register_bc01` | OK | Nombre exacto del maestro sin extensión, no duplica ID; toma Configuración y cantidad de filas. |
| `quitarExtension_` | `utils.remove_xlsx_extension` | OK | Regex .xlsx al final, case-insensitive, luego trim. |
| `normalizarTexto_` | `utils.normalize_simple` | OK | Quita tildes y hace trim/lowercase; mantiene puntuación y espacios interiores. |
| `eliminarTriggersPDV_` | `PdvCreationService.start_mass_creation` + bloqueo de ejecución | OK | En Python no se crean triggers; una única ejecución secuencial controlada sustituye su coordinación. No elimina triggers del proyecto original. |
| `doGet` | `web_controller.index` | OK | GET / con título Inventarios PDV; HTTP 200 comprobado. |
| `obtenerLibroMaestro_` | `MasterSheetRepository` | OK | Mismo ID en .env. |
| `obtenerPuntosVenta` | `InventoryService.get_points_of_sale` | OK | B/C/D, LISTO, trim, deduplicación por nombre exacto y orden español. |
| `obtenerCategorias` | `InventoryService.get_categories` | OK | Categorías únicas extraídas de productos. |
| `obtenerProductos` | `InventoryService.get_products` | OK | Encabezados alternativos, fallback A:D, display/raw separados, categoría por defecto Uno a Uno. |
| `guardarInventario` | `InventoryService.save_inventory` | OK | UUID común, 12 columnas, cantidades y factor en backend, bloqueo y duplicado; mocks cubren envío completo. |
| `actualizarResumenInventario_` | `InventorySummaryService.update_pdv_summary` | OK | Fecha/PDV normalizado/item, primer factor, suma Cerrado/Abierto y recalcula físico; limpia solo contenidos. |
| `registrarEnResumenGeneral_` | `InventorySummaryService.register_general_summary` | OK | Incrementa Cerrado, Abierto y físico anterior; reemplaza metadatos con el registro nuevo. |
| `reconstruirResumenGeneral` | `InventorySummaryService.rebuild_general_summary` | OK | Solo LISTO, recalcula físico individual, agrupa, ordena, limpia y reescribe. CLI pide ejecución consciente. |
| `agregarRegistroResumen_` | `InventorySummaryService.aggregate` | OK | Primer factor/metadatos por grupo y acumulación de los tres totales. |
| `claveResumenGeneral_` | `utils.summary_key` | OK | Fecha, PDV normalizado e item sin crear identificadores. |
| `encabezadosResumenGeneral_` | `constants.SUMMARY_HEADERS` | OK | Diez encabezados exactos. |
| `obtenerHojaResumenGeneral_` | `GeneralSummaryRepository.ensure_sheet` | OK | Reutiliza hoja exacta o renombra la primera vacía, o crea otra. |
| `prepararHojaResumenGeneral_` | `GeneralSummaryRepository.prepare` | OK | Encabezado solo si la hoja está vacía. |
| `obtenerFactoresPorItem_` | `PdvSheetRepository.factors` | OK | Exige columna Item y Factor, usa valores raw y última ocurrencia del item. |
| `convertirNumero_` | `utils.convert_number` | OK | Vacío/null a fallback; primera coma a punto; conversión numérica. |
| `normalizarFactor_` | `utils.normalize_factor` | OK | Divide repetidamente por 10000 mientras factor >= 10000. |
| `obtenerFactorCorrecto_` | `utils.correct_factor` | OK | X número tiene prioridad, después factor normalizado, finalmente 1. |
| `aplicarFormatoResumen_` | `GoogleSheetsService.format_header` | OK | #4A2B14, blanco, negrita, congelación y autoajuste. |
| `claveFecha_` | `utils.date_key` | OK | Date en huso configurado, ISO y DD/MM o DD-MM; no interpreta otros formatos. |
| `obtenerLibroPDV_` | `MasterSheetRepository.pdv_book` / `PdvSheetRepository.book` | OK | Compara el nombre exacto del PDV; estado LISTO y URL existente. |
| `buscarHoja_` | `GoogleSheetsService.find_sheet(normalized=True)` | OK | Usa normalización backend; la creación masiva conserva la variante simple del otro script. |
| `buscarIndice_` | `utils.find_index` | OK | Primer encabezado que coincide con alguna opción normalizada. |
| `normalizar_` | `utils.normalize` | OK | NFD, tildes, .-_ a espacios, compacta espacios, trim y lowercase. |
| `actualizarTodasLasBasesUDM` | `UdmService.update_all` / `update_pdv` | OK | Por nombre normalizado, crea columnas faltantes, conserva valores no encontrados, log de 6 columnas. |

## Frontend

La columna de implementación identifica JavaScript cuando la función permanece en el navegador. El cuerpo HTML y CSS se comparan automáticamente con el original; no se hizo inspección visual en un navegador real porque no hay uno conectado en esta sesión.

| Función original | Implementación Python / navegador | Estado | Observaciones |
|---|---|---|---|
| `asignarFechaActual` | `static/js/inventory.js` | OK | Fecha local del navegador. |
| `cargarPuntosVenta` | JS + GET `/api/puntos-venta` | OK | Callback original conservado; transporte fetch. |
| `cargarCategoriasPDV` | JS + GET `/api/categorias` | OK | Mismos selectores, estados y mensajes. |
| `comenzarInventario` | JS + GET `/api/productos` | OK | Mismas validaciones, carga, borrador y pantalla. |
| `prepararInventario` | `static/js/inventory.js` | OK | PDV, fecha y categoría del resumen. |
| `mostrarProductos` | `static/js/inventory.js` | OK | Tarjetas, búsqueda Item+Producto, escape HTML. |
| `registrarCantidad` | `static/js/inventory.js` | OK | Guarda borrador y actualiza progreso. |
| `actualizarProgreso` | `static/js/inventory.js` | OK | Ambas casillas no vacías; redondeo original. |
| `completarVaciosConCero` | `static/js/inventory.js` | OK | Cuenta casillas, confirma y guarda ceros. |
| `guardarInventario` (frontend) | JS + POST `/api/inventarios` | OK | Payload y mensajes conservados; error no elimina borrador. |
| `nuevoInventario` | `static/js/inventory.js` | OK | Limpia selección y vuelve al inicio. |
| `guardarBorrador` | `static/js/inventory.js` | OK | localStorage por item; mismo contenido. |
| `recuperarBorrador` | `static/js/inventory.js` | OK | Recupera por item al entrar de nuevo. |
| `eliminarBorrador` | `static/js/inventory.js` | OK | Solo después de éxito. |
| `obtenerClaveBorrador` | `static/js/inventory.js` | OK | inventario-uno-a-uno-v3-PDV-FECHA-CATEGORIA exacto. |
| `mostrarMensaje` | `static/js/inventory.js` | OK | Texto y clase originales. |
| `ocultarMensaje` | `static/js/inventory.js` | OK | Restablece el mensaje. |
| `obtenerMensajeError` | `static/js/inventory.js` | OK | Error.message original, errores HTTP traducidos por fetchJSON. |
| `formatearFecha` | `static/js/inventory.js` | OK | DD/MM/YYYY. |
| `normalizarTexto` | `static/js/inventory.js` | OK | Variante frontend sin reemplazar puntuación. |
| `escaparHTML` | `static/js/inventory.js` | OK | Misma sustitución de &, <, >, comillas. |

## Particularidades conservadas y límites de la verificación

- Si falta la columna Factor, `obtenerFactoresPorItem_` devuelve un mapa vacío. El guardado usa 1 incluso si el frontend mostró un factor deducido de UDM. Se conservó y se probó.
- `obtenerProductos` filtra filas antes de aplicar la posición al array raw del factor. Ante huecos, puede mostrar el factor raw de otra fila. Se conservó esa posición; al guardar se relee el mapa por item.
- El resumen PDV mantiene el primer factor; el general normal suma físicos individuales. La reconstrucción ignora el físico guardado y vuelve a calcularlo. Hay pruebas con factores distintos en el mismo grupo.
- Los inputs vacíos individuales se convierten en 0 en backend; las filas con ambos vacíos se omiten. La UI conserva la exigencia de completar ambos campos antes de enviar.
- Los borradores conservan clave y formato, pero localStorage pertenece al origen web: los borradores guardados en el dominio anterior de Apps Script no son accesibles desde localhost u otro dominio.
- Los arrays de Sheets se leen como valores mostrados o tipados según el método original. Las fechas numéricas se convierten usando el formato efectivo y huso del documento. Los textos se escriben como `stringValue` para conservar códigos como `001` y evitar inyección de fórmulas.
- La ordenación usa Unicode Collation con tratamiento de ñ y orden numérico de items. Se comprueba con el motor JavaScript en las pruebas; las listas de los 35 PDV y sus productos también se leyeron con las credenciales reales durante la revisión.
- Se rechazan Infinity y resultados no finitos en backend, tal como permite la regla de validación de la misión; no son números representables en la API JSON de Google.
- No hay transacción entre documentos ni rollback automático. Un fallo tras escribir Conteos puede dejar un resumen sin actualizar, igual que en el legacy. Los locks de Python no coordinan escritores externos ni varias instancias con filesystems distintos.

Las llamadas FormApp conservadas son `setConfirmationMessage`, `setProgressBar`, `createTextValidation`, `requireNumberGreaterThanOrEqualTo`, `setHelpText`, `build`, `setValidation`, `setDestination`, `getPublishedUrl` y `getEditUrl`, con `openById`/`getItems` para acceder al Form creado por REST. La razón y el despliegue están en [compat/README.md](compat/README.md). El campo de destino de [Forms REST es solo lectura](https://developers.google.com/workspace/forms/api/reference/rest/v1/forms); no se inventó un método Python para editarlo.

La conversión utiliza descarga binaria del XLSX y subida a [Drive files.create con el MIME de Google Sheets](https://developers.google.com/workspace/drive/api/guides/manage-uploads). Drive realiza la conversión; Python no reinterpreta el Excel.

# Verificaciones de la primera versión

Fecha: 8 de septiembre de 2026. Entorno: Windows, Python 3.12.10 local al proyecto y Node.js 24.19.0.

| Verificación | Resultado |
|---|---|
| Instalación en `.venv` | Correcta; versiones guardadas en `requirements-lock.txt` |
| `python -m pytest -q` | **81 passed**, sin pruebas omitidas |
| `python -m pip check` | `No broken requirements found.` |
| `python -m compileall -q app scripts run.py` | Correcto |
| `node --check app/static/js/inventory.js` | Correcto |
| `python run.py`, consulta HTTP local | Inició; GET `/` devolvió 200 y título Inventarios PDV |
| Endpoints GET y POST | Verificados con repositorios de prueba; éxito y duplicado |
| HTML/CSS respecto al legacy | Cuerpo HTML y CSS idénticos mediante comparación automática |
| Flujo JavaScript | Probado con DOM simulado y fetch mock: selección, carga, búsqueda, borrador, recuperación, progreso, completar, error, éxito y reinicio |
| Comparación con Apps Script original | Normalización, factores, fechas, claves, orden español y flujos completos de guardado, reconstrucción y UDM, con hojas simuladas |
| Concurrencia | Dos envíos simultáneos: solo uno aceptado; bloqueo del sistema operativo comprobado entre procesos |
| Schemas Google | Payloads de Forms, Sheets y conversión Drive verificados contra discovery oficial instalado |
| `python scripts/verify_google_access.py` | Terminó con error específico: falta cliente OAuth `credentials/credentials.json` |
| Acceso a documentos Google reales | No validado: faltan credenciales |
| Escrituras reales / creación Forms / despliegue GCP | No ejecutados |
| Navegador real / revisión visual | No disponible: no hay navegador conectado a la herramienta de UI |
| Docker | Archivo preparado; imagen no construida ni probada en este entorno |

Las pruebas impiden que `GoogleAuthService.api` contacte Google. Solo los mocks manipulan las hojas simuladas en RAM dentro de `tests/`; la aplicación productiva no tiene persistencia alternativa ni modo de datos ficticios.

Las pruebas diferenciales ejecutan el código original con Node y comparan su salida con Python. Los UUID y fechas de ejecución se sustituyen por marcadores únicamente al comparar fixtures; en la aplicación son UUID estándar y fechas reales.

La paridad real de permisos, formatos existentes, cuotas, publicación de Forms, validaciones de respuesta y vínculo de respuestas a Sheets debe comprobarse después de autorizar la misma cuenta Google. La matriz completa y los detalles históricos conservados están en [MIGRATION_PARITY.md](MIGRATION_PARITY.md).

Siguiente paso: colocar el cliente OAuth de escritorio en `credentials/credentials.json`. Después, ejecutar `python scripts/verify_google_access.py`; no modifica documentos Google. Para crear nuevos PDV también se requiere desplegar el adaptador descrito en [compat/README.md](compat/README.md).

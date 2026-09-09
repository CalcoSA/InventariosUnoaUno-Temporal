# Despliegue manual en calco-feplanb — Debian, Apache y Gunicorn

**Primera fase: inspeccionar el servidor.** Esta guía prepara acciones que realizará el administrador; no se ejecutó ningún despliegue desde Codex. Servidor previsto: `calco-feplanb`, Debian 12. Dominio: `inventariospdv-v2.calcoweb.net`. Código exclusivamente en `/opt/apps/inventarios-uno-a-uno`.

**NO TOCAR `/opt/apps/deliveryTraceability`.** No cambiar su propietario, permisos, código, servicio ni vhost. No ejecutar `chown -R` sobre `/opt/apps`. No modificar vhosts existentes sin identificarlos primero. Mantener la Web App/Apps Script legacy y el Woody anterior disponibles hasta aceptar el cambio de operación.

## 1. Inspección obligatoria antes de instalar o cambiar nada

Ejecutar manualmente en el servidor y revisar las salidas:

```bash
hostname
cat /etc/os-release
python3 --version
git --version
apache2 -v
sudo apache2ctl -S
sudo apache2ctl -M
df -h
free -h
ls -lah /opt/apps
sudo ls -lah /etc/apache2/sites-available
sudo ls -lah /etc/apache2/sites-enabled
sudo grep -R "inventariospdv" /etc/apache2/sites-available /etc/apache2/sites-enabled
sudo grep -R "SSLCertificateFile" /etc/apache2/sites-available /etc/apache2/sites-enabled
sudo find /etc/letsencrypt/live -maxdepth 2 -type f 2>/dev/null
sudo ss -ltnp
timedatectl status
```

El `find` pedido puede no mostrar certificados que sean enlaces simbólicos: inspeccionar también con `sudo ls -lah /etc/letsencrypt/live` si el directorio existe y `readlink -f` sobre las rutas descubiertas. No se presupone que exista Let's Encrypt, Certbot ni un certificado concreto.

Desde el cliente:

```text
nslookup inventariospdv-v2.calcoweb.net
```

Confirmar la IP externa real de `calco-feplanb` en GCP y compararla con DNS; no se ha comprobado que coincidan. Verificar reloj/NTP también en WordPress (tolerancia SSO máxima 10 s). Si 8000 ya tiene un listener, identificarlo y detener esta instalación hasta resolver la colisión; no detener procesos de otra aplicación.

## 2. Dependencias Debian y usuario dedicado

Instalar únicamente lo que falta según la inspección; no reinstalar ni sustituir Apache existente:

```bash
sudo apt-get update
sudo apt-get install python3 python3-venv python3-pip git ca-certificates openssl curl nodejs
getent passwd inventarios
getent group inventarios
```

Node solo se usa para pruebas; es necesario para no omitir la paridad JavaScript y los casos de varias pestañas. Si el usuario/grupo ya existe, comprobar su propósito antes de reutilizarlo. Si no existe:

```bash
sudo useradd --system --user-group --create-home --home-dir /var/lib/inventarios-uno-a-uno --shell /usr/sbin/nologin inventarios
sudo install -d -o inventarios -g inventarios -m 0750 /opt/apps/inventarios-uno-a-uno
sudo install -d -o root -g inventarios -m 0750 /etc/inventarios-uno-a-uno
sudo install -d -o inventarios -g inventarios -m 0750 /var/lib/inventarios-uno-a-uno
sudo install -d -o inventarios -g inventarios -m 0750 /var/lock/inventarios-uno-a-uno
readlink -f /var/lock
```

En Debian `/var/lock` suele resolver a `/run/lock`; confirmar esa equivalencia. El unit usa `RuntimeDirectory=lock/inventarios-uno-a-uno`, que recrea el directorio con propietario correcto al iniciar el servicio, incluso después de reboot, y `RuntimeDirectoryPreserve=yes` para no eliminar locks de comandos administrativos al detener/reiniciar Gunicorn. No usar un lock de otra aplicación. Si tras un reboot se va a ejecutar una CLI antes del servicio, recrear exactamente el directorio anterior.

## 3. GitHub Deploy Key de solo lectura y clone

Si el repositorio es privado, usar una clave SSH exclusiva de lectura. No guardar PAT, contraseñas o claves SSH privadas dentro del repositorio. La clave SSH de GitHub es distinta de la clave RSA SSO.

```bash
sudo install -d -o inventarios -g inventarios -m 0700 /var/lib/inventarios-uno-a-uno/.ssh
sudo -u inventarios ssh-keygen -t ed25519 -C inventarios-uno-a-uno-readonly -N '' -f /var/lib/inventarios-uno-a-uno/.ssh/id_ed25519
sudo -u inventarios cat /var/lib/inventarios-uno-a-uno/.ssh/id_ed25519.pub
```

Registrar **solo esa pública** en GitHub → repositorio → Deploy keys, sin habilitar escritura. Comprobar la huella del host GitHub por un canal oficial/administrativo antes de aceptar el primer SSH; no desactivar `StrictHostKeyChecking`. Una vez comprobada:

```bash
sudo -u inventarios -H ssh -T git@github.com
```

La respuesta de GitHub puede terminar con código 1 aunque la autenticación sea correcta porque no ofrece shell. Sustituir `ORGANIZACION/REPOSITORIO` por la ruta real del repositorio actual; no es un valor para copiar literalmente:

```bash
sudo -u inventarios -H git clone git@github.com:ORGANIZACION/REPOSITORIO.git /opt/apps/inventarios-uno-a-uno
sudo -u inventarios git -C /opt/apps/inventarios-uno-a-uno status --short
sudo -u inventarios git -C /opt/apps/inventarios-uno-a-uno rev-parse HEAD
```

El destino debe estar vacío para el clone. Si ya contiene un checkout, identificar rama, cambios y origen antes de usar la actualización del apartado 15. Los cambios de esta fase deben estar revisados y publicados en la rama que se clone; esta tarea no hizo commit ni push.

## 4. Virtualenv, dependencias y suite aislada

```bash
sudo -u inventarios python3 -m venv /opt/apps/inventarios-uno-a-uno/.venv
sudo -u inventarios /opt/apps/inventarios-uno-a-uno/.venv/bin/python -m pip install -r /opt/apps/inventarios-uno-a-uno/requirements.txt
sudo -u inventarios /opt/apps/inventarios-uno-a-uno/.venv/bin/python -m pip check
cd /opt/apps/inventarios-uno-a-uno
sudo -u inventarios env APP_ENV=testing AUTH_ENABLED=false FLASK_DEBUG=false /opt/apps/inventarios-uno-a-uno/.venv/bin/python -B -m pytest -q -p no:cacheprovider
```

`requirements-lock.txt` refleja Windows; para Debian usar `requirements.txt`, que incluye Gunicorn con un marcador de plataforma. Las pruebas bloquean Google y usan datos simulados. No crear un `.env` de desarrollo en el checkout de producción: la configuración de servicio se mantiene en `/etc`. Ejecutar siempre pytest desde la raíz, pues algunas comparaciones leen archivos relativos.

## 5. Claves SSO: generar únicamente en el servidor WordPress

Identificar el usuario/grupo real de PHP-FPM o Apache que ejecuta WordPress. No asumir que sea `www-data`. En ese servidor, y solo allí:

```bash
sudo mkdir -p /etc/calco-intranet/inventario-uno-a-uno
sudo openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem
sudo openssl rsa -pubout -in /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem -out /etc/calco-intranet/inventario-uno-a-uno/sso_public.pem
```

Reemplazar `GRUPO_PHP_CONFIRMADO` por el grupo verificado; limitar lectura de la privada al runtime WordPress:

```bash
sudo chown root:GRUPO_PHP_CONFIRMADO /etc/calco-intranet/inventario-uno-a-uno
sudo chmod 0750 /etc/calco-intranet/inventario-uno-a-uno
sudo chown root:GRUPO_PHP_CONFIRMADO /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem
sudo chmod 0640 /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem
sudo chmod 0644 /etc/calco-intranet/inventario-uno-a-uno/sso_public.pem
```

No regenerar claves encima de archivos existentes sin plan de rotación. Copiar a `calco-feplanb` **solo `sso_public.pem`** por un canal seguro. **Nunca copiar la privada a GCP, Flask, `.env`, GitHub, Woody como literal o JavaScript.** Comprobar que PHP tenga OpenSSL y permiso de lectura; si tiene `open_basedir`, incluir el directorio privado de manera específica.

## 6. Credenciales Google y permisos en GCP

Transferir los archivos vigentes mediante canal seguro a un área privada del administrador. Sustituir las rutas de origen verificadas en estos comandos, sin imprimir los contenidos:

```bash
sudo install -o root -g inventarios -m 0640 /RUTA_PRIVADA/credentials.json /etc/inventarios-uno-a-uno/credentials.json
sudo install -o inventarios -g inventarios -m 0600 /RUTA_PRIVADA/token.json /var/lib/inventarios-uno-a-uno/token.json
sudo install -o root -g inventarios -m 0640 /RUTA_PRIVADA/sso_public.pem /etc/inventarios-uno-a-uno/sso_public.pem
```

El token **y su directorio** deben ser escribibles por `inventarios`: GoogleAuthService escribe un temporal y lo renombra al refrescar. No sustituir el cliente OAuth por Service Account. La pública SSO y el cliente Google solo necesitan lectura. No modificar otros directorios ni permisos globales de `/etc`, `/var/lib` o `/var/lock`.

## 7. Configuración de producción y secreto independiente

Crear el archivo antes de editarlo:

```bash
sudo install -o root -g inventarios -m 0640 /dev/null /etc/inventarios-uno-a-uno/inventarios.env
sudoedit /etc/inventarios-uno-a-uno/inventarios.env
```

Contenido (copiar, ajustar solo los valores pendientes; no dejar el secreto vacío):

```dotenv
APP_ENV=production
AUTH_ENABLED=true
FLASK_ENV=production
FLASK_DEBUG=false
SSO_ISSUER=calco-intranet
SSO_AUDIENCE=inventarios-uno-a-uno
SSO_PUBLIC_KEY_PATH=/etc/inventarios-uno-a-uno/sso_public.pem
SSO_TOKEN_MAX_AGE_SECONDS=60
SSO_CLOCK_SKEW_SECONDS=10
SESSION_JWT_SECRET=
SESSION_JWT_ISSUER=inventarios-uno-a-uno
SESSION_JWT_AUDIENCE=inventarios-session
SESSION_JWT_COOKIE_NAME=inventario_session
SESSION_IDLE_TIMEOUT_SECONDS=1200
SESSION_COOKIE_SECURE=true
INTRANET_URL=
APP_TIMEZONE=America/Bogota
GOOGLE_MASTER_SPREADSHEET_ID=1q34wHfO08PDclMA2zSNf03naVkSllG6lCRcHu6dGdg4
GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID=1_Kj9mXyd5q8y1wx6D0sSmbapiGugvxj3yBo437xQk8M
GOOGLE_CREDENTIALS_PATH=/etc/inventarios-uno-a-uno/credentials.json
GOOGLE_TOKEN_PATH=/var/lib/inventarios-uno-a-uno/token.json
GOOGLE_FORMS_COMPAT_SCRIPT_ID=
GOOGLE_HTTP_TIMEOUT=60
INVENTORY_LOCK_PATH=/var/lock/inventarios-uno-a-uno/inventory.lock
```

`INTRANET_URL` queda vacío hasta conocer su URL HTTPS real. El adaptador puede seguir vacío para inventarios existentes; ver apartado 14 antes de crear PDV.

El secreto se genera **en GCP** con `openssl rand -hex 32`. Para guardarlo sin mostrarlo en terminal/historial y sin ponerlo como argumento de proceso, realizar esta operación una sola vez después de guardar el archivo anterior:

```bash
sudo /opt/apps/inventarios-uno-a-uno/.venv/bin/python - <<'PY'
from pathlib import Path
import subprocess
p = Path('/etc/inventarios-uno-a-uno/inventarios.env')
text = p.read_text()
lines = text.splitlines()
assert sum(line.startswith('SESSION_JWT_SECRET=') for line in lines) == 1
assert 'SESSION_JWT_SECRET=' in lines, 'Ya existe un secreto: no rotarlo automáticamente'
secret = subprocess.check_output(['openssl', 'rand', '-hex', '32'], text=True).strip()
p.write_text('\n'.join('SESSION_JWT_SECRET=' + secret if line == 'SESSION_JWT_SECRET=' else line for line in lines) + '\n')
PY
```

No imprimir `inventarios.env` ni copiar ese secreto a WordPress. La aplicación rechazará arrancar si producción no tiene autenticación, cookie Secure, pública válida, secreto suficiente o si tiene debug activo. No utilizar `--print-config` con variables sensibles ni comandos que impriman todo el entorno.

## 8. Verificar carga WSGI/Gunicorn y Google sin escribir datos

Estas comprobaciones no abren puerto. Cargar el EnvironmentFile privado mediante python-dotenv, sin hacer `source` de valores arbitrarios:

```bash
cd /opt/apps/inventarios-uno-a-uno
sudo -u inventarios .venv/bin/python -B - <<'PY'
from dotenv import load_dotenv
load_dotenv('/etc/inventarios-uno-a-uno/inventarios.env', override=True)
from gunicorn.util import import_app
app = import_app('wsgi:app')
assert app.test_client().get('/healthz').json == {'status': 'ok'}
assert app.test_client().get('/').status_code == 401
print('Carga Gunicorn/WSGI y bloqueo de acceso: OK')
PY
sudo -u inventarios .venv/bin/python -B - <<'PY'
import os
from dotenv import load_dotenv
load_dotenv('/etc/inventarios-uno-a-uno/inventarios.env', override=True)
os.execv('.venv/bin/gunicorn', ['gunicorn', '--check-config', '--bind', '127.0.0.1:8000', '--workers', '1', '--threads', '4', 'wsgi:app'])
PY
```

Verificar primero credenciales de forma **no interactiva**, para que el servidor no intente abrir un callback OAuth. Después reutilizar el verificador real, que solo lee Google:

```bash
sudo -u inventarios .venv/bin/python -B - <<'PY'
import sys
from dotenv import load_dotenv
load_dotenv('/etc/inventarios-uno-a-uno/inventarios.env', override=True)
from app import create_app
app = create_app()
try:
    app.extensions['services']['auth'].credentials(interactive=False)
except Exception:
    raise SystemExit('OAuth no disponible: revisar permisos/scopes y autorizar desde una máquina con navegador. No se borró el token.')
sys.path.insert(0, 'scripts')
from verify_google_access import verify
raise SystemExit(verify(app))
PY
```

Esperar autenticación, maestro, Control Formularios, UDM, general, Drive, carpeta y Form existente correctos. `SKIP Forms API` no equivale a Forms validado. El refresco puede actualizar el archivo local token; no escribe documentos. Revisar conectividad HTTPS saliente a Google APIs y OAuth; no aplicar reglas de firewall o systemd que impidan esa salida. Un error de socket no se arregla borrando el token.

**No ejecutar aquí** POST `/api/inventarios`, `scripts/create_all_pdv.py`, `scripts/update_all_udm.py` ni `scripts/rebuild_general_summary.py` contra Google real.

## 9. Instalar systemd e iniciar Gunicorn manualmente

Inspeccionar si ya existe un unit con ese nombre y respaldarlo antes de sustituirlo. El archivo preparado es [deploy/inventarios-uno-a-uno.service](../deploy/inventarios-uno-a-uno.service).

```bash
sudo install -o root -g root -m 0644 deploy/inventarios-uno-a-uno.service /etc/systemd/system/inventarios-uno-a-uno.service
sudo systemd-analyze verify /etc/systemd/system/inventarios-uno-a-uno.service
sudo systemctl daemon-reload
sudo systemctl enable inventarios-uno-a-uno
sudo systemctl start inventarios-uno-a-uno
sudo systemctl status inventarios-uno-a-uno --no-pager
sudo journalctl -u inventarios-uno-a-uno -n 50 --no-pager
sudo ss -ltnp 'sport = :8000'
curl -i http://127.0.0.1:8000/healthz
```

Confirmar `200 {"status":"ok"}` y escucha **solo 127.0.0.1:8000**, nunca `0.0.0.0:8000`. Producción no usa `python run.py`. El unit ejecuta `wsgi:app`, un worker, cuatro threads, usuario/grupo `inventarios`, `Restart=on-failure`, `NoNewPrivileges=true` y `PrivateTmp=true`. Mantiene red saliente disponible y deja 330 s para terminar operaciones en curso al detener; no forzar el corte de un guardado.

No aumentar workers: el replay cache es memoria del proceso. No hacer reload gradual de workers. La [guía de autenticación](AUTENTICACION_SSO.md) documenta reinicios, varias pestañas y límites de revocación.

## 10. Apache: inspección, módulos y certificado existente

Volver a revisar `sudo apache2ctl -S`, `sudo apache2ctl -M`, sites-available/sites-enabled y los grep del apartado 1. Identificar el vhost actual del dominio y su certificado; no crear dos vhosts activos para el mismo ServerName. Si existe uno, planear su sustitución con respaldo y rollback específico, sin tocar otros dominios.

Solo si faltan, habilitar manualmente los módulos requeridos:

```bash
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod headers
sudo a2enmod rewrite
sudo a2enmod ssl
```

Revisar [deploy/apache-inventariospdv-v2.conf](../deploy/apache-inventariospdv-v2.conf). Tiene `ProxyPass`, `ProxyPassReverse`, `ProxyPreserveHost`, redirección HTTP→HTTPS y un único proxy local confiable. Los placeholders **`__VERIFIED_SSLCertificateFile__`** y **`__VERIFIED_SSLCertificateKeyFile__`** deben reemplazarse por las rutas reales verificadas. No activar el archivo sin reemplazarlos. No se han inventado rutas SSL.

```bash
sudo install -o root -g root -m 0644 deploy/apache-inventariospdv-v2.conf /etc/apache2/sites-available/apache-inventariospdv-v2.conf
sudoedit /etc/apache2/sites-available/apache-inventariospdv-v2.conf
```

Comprobar que el certificado incluye el dominio, fechas, cadena y correspondencia con la clave (usar rutas ya identificadas):

```bash
sudo openssl x509 -in /RUTA_SSL_CONFIRMADA/CERTIFICADO -noout -subject -issuer -dates -ext subjectAltName
sudo openssl x509 -in /RUTA_SSL_CONFIRMADA/CERTIFICADO -pubkey -noout | openssl sha256
sudo openssl pkey -in /RUTA_SSL_CONFIRMADA/CLAVE -pubout | openssl sha256
```

Las dos huellas públicas deben coincidir; no imprimir la clave privada. Si no hay certificado válido, obtenerlo con el procedimiento corporativo antes de activar HTTPS. No instalar ni ejecutar Certbot sin revisar la gestión actual. Comprobar DNS otra vez y reglas de entrada 80/443 para este servicio; **no abrir 8000 en GCP ni en el host**.

Los logs configurados usan `%U` (ruta) y omiten query/body/cookies. Verificar también que reglas globales, WAF/ModSecurity, trazas PHP, plugins de caché o diagnóstico no registren cuerpos de `/auth/sso`/`admin-post.php` ni cookies. No habilitar debug en producción.

## 11. Validar y activar exclusivamente el vhost identificado

Antes de habilitar el sitio, incluir solo el candidato en una comprobación sin recargar Apache:

```bash
sudo apache2ctl -t -c 'Include /etc/apache2/sites-available/apache-inventariospdv-v2.conf'
sudo apache2ctl configtest
```

Si el dominio tenía un vhost anterior, anotar su nombre exacto, respaldar el archivo y deshabilitar **solo ese** en la ventana de cambio; no copiar un nombre supuesto en `a2dissite`. Después:

```bash
sudo a2ensite apache-inventariospdv-v2.conf
sudo apache2ctl configtest
sudo apache2ctl -S
sudo systemctl reload apache2
```

Recargar solo si configtest da `Syntax OK` y el mapa confirma el dominio correcto. Si falla, deshabilitar el candidato, restaurar el sitio anterior identificado y volver a validar sin recargar una configuración inválida. Las conexiones de los otros vhosts deben conservarse; comprobar sus healthchecks existentes sin modificarlos.

Desde cliente externo, **antes de probar SSO**:

```bash
curl -i https://inventariospdv-v2.calcoweb.net/healthz
curl -I http://inventariospdv-v2.calcoweb.net/healthz
```

Esperar 200 y JSON en HTTPS, 308 hacia HTTPS en HTTP. No usar `curl -k`; un error de certificado debe corregirse. Abrir `/` en una ventana privada sin cookie: debe mostrar acceso requerido con 401. `/api/puntos-venta` sin cookie debe devolver 401 con mensaje de sesión. Una pestaña que ya conserva cookie válida puede entrar directamente: la comprobación de acceso inicial se hace sin cookie.

## 12. Woody, login y prueba de sesión

Guardar una copia privada del Woody anterior y mantener el deployment legacy. En WordPress verificar PHP >=7.3 y OpenSSL. Copiar **todo** [deploy/woody_sso_snippet.php](../deploy/woody_sso_snippet.php) en un snippet PHP de ejecución global, incluido admin (`Run everywhere`); omitir la etiqueta inicial `<?php` si el editor la añade. Usar en la página protegida `[inventarios_pdv_sso]`. No elegir el modo que ejecuta el PHP solamente al renderizar un shortcode de Woody: los hooks `admin_post` deben registrarse también en esa nueva solicitud. No activar dos veces el mismo código.

Antes de guardar en Woody puede verificar `php -l woody_sso_snippet.php` en WordPress. Excluir del caché de página la vista de usuarios autenticados y `admin-post.php`. El snippet verifica nonce, login y usuario vigente al hacer click; no usa roles adicionales. Si se configura `INVENTARIOS_SSO_TTL_SECONDS` en `wp-config.php`, hacer coincidir el máximo aceptado por Flask (por defecto 60).

Prueba manual sin guardar inventarios:

1. Iniciar sesión en la intranet y pulsar **INVENTARIOS PDV**. Debe abrir una sola pestaña nueva, pasar por POST a WordPress y POST a `/auth/sso`, terminar en `/` sin token/query string y cargar el inventario.
2. Inspeccionar **atributos**, sin copiar el valor: cookie `inventario_session`, HttpOnly, Secure, SameSite Lax, Path `/`, sin Domain. No pegar JWT en consola ni exportar un HAR con secretos.
3. Consultar PDV, categorías y productos. Introducir algunos Cerrado/Abierto para producir un borrador; **no pulsar Guardar**.
4. Mantener actividad durante más de 20 minutos: debe seguir válida. Dejar luego 20 minutos sin click, teclado, scroll, tacto ni mouse en **todas** las pestañas: debe aparecer el mensaje de cierre. Cambiar pestañas o mover el ratón sobre la app cuenta como actividad.
5. Mantener una pestaña A quieta y usar B; A no debe cerrar la sesión de B. Repetir tras suspender y reactivar A. El backend rechaza sesiones vencidas aunque se detengan los temporizadores JS.
6. Reingresar desde la intranet, elegir el mismo PDV/fecha/categoría y comprobar la recuperación exacta del borrador. No limpiar datos del navegador ni cambiar de origen para esta comprobación.
7. Logout explícito mediante POST con la cabecera de la aplicación debe borrar la cookie y conservar borradores. No reutilizar el JWT SSO: el segundo uso se rechaza.

Para ver rápidamente la lógica temporal, ejecutar la suite con reloj simulado; no reducir el timeout de producción por conveniencia de prueba. Las pruebas automatizadas no sustituyen esta aceptación real de WordPress/Apache/navegador.

## 13. Primera escritura controlada: posterior, nunca durante esta preparación

Solo después de aceptar login, lecturas PDV/categorías/productos, borrador, varias pestañas y timeout, programar **una prueba de escritura controlada** con un PDV y fecha/categoría acordados. Respaldar previamente **la base Google Sheet completa del PDV de prueba** y **el Spreadsheet Resumen General**. Evitar escritores legacy simultáneos. Comprobar detalle, Resumen Inventario, Resumen General y eliminación del borrador solo tras éxito. Documentar el resultado y cualquier dato de prueba; no borrar datos indiscriminadamente. No ejecutar desde Codex como parte de esta tarea.

## 14. Google Forms compat: pendiente independiente

La creación completa de nuevos PDV requiere desplegar `compat/forms_adapter.gs` con su manifiesto en un proyecto dedicado, como **Ejecutable de API**, y vincularlo al mismo proyecto estándar Cloud del cliente OAuth. Configurar `GOOGLE_FORMS_COMPAT_SCRIPT_ID` con el **Deployment ID de ese ejecutable**, no el Script ID de Configuración del proyecto. El discovery instalado mantiene el nombre `scriptId`, pero especifica que para el IDE nuevo debe recibir DeploymentID. Detalle y fuentes en [compat/README.md](../compat/README.md).

El ID local está vacío y el token local no incluye `https://www.googleapis.com/auth/forms`. Para las lecturas/guardado actuales no hace falta regenerar OAuth. **Al habilitar compat hará falta consentimiento adicional** desde una máquina con navegador, mismo cliente/proyecto e ID ya configurado. El verificador interactivo detecta scopes faltantes; no borrar automáticamente el token. Copiar el token actualizado a la ruta privada de GCP y comprobar permisos. No ejecutar el adaptador como una prueba de lectura: modifica el Form. Su despliegue y la aceptación de creación completa siguen pendientes; no se realizaron ahora.

## 15. Rollback y futuras actualizaciones

Antes del cambio, conservar enlace Woody anterior, Apps Script/Web App legacy, vhost anterior identificado y SHA de la versión aceptada. No eliminar deployments o Apps Scripts durante el despliegue inicial. Si Flask falla:

1. Deshabilitar el nuevo enlace Woody y volver al enlace legacy previamente conservado.
2. Detener solamente `inventarios-uno-a-uno.service` (esperar a que terminen solicitudes en curso).
3. Si se cambió el vhost, deshabilitar solo `apache-inventariospdv-v2.conf`, restaurar/habilitar el vhost anterior identificado, ejecutar `apache2ctl configtest` y recargar Apache únicamente si pasa.
4. No borrar Google Sheets, Forms, conteos, resúmenes, token ni borradores. No tocar deliveryTraceability. No operar simultáneamente escritores Flask y legacy.

```bash
sudo systemctl stop inventarios-uno-a-uno
sudo systemctl is-active inventarios-uno-a-uno
sudo ss -ltnp 'sport = :8000'
```

Para actualizar, cerrar temporalmente acceso Woody y esperar a terminar capturas/guardados. Registrar SHA previo y exigir checkout limpio. Dejar el SSO cerrado al menos `max(90, SSO_TOKEN_MAX_AGE_SECONDS + 2 × SSO_CLOCK_SKEW_SECONDS)` segundos durante el mantenimiento para agotar tokens en tránsito; un reinicio pierde el replay cache. Con defaults son 90 s. No usar reload gradual de Gunicorn.

```bash
sudo systemctl stop inventarios-uno-a-uno
sudo -u inventarios git -C /opt/apps/inventarios-uno-a-uno status --short
sudo -u inventarios git -C /opt/apps/inventarios-uno-a-uno rev-parse HEAD
sudo -u inventarios -H git -C /opt/apps/inventarios-uno-a-uno pull --ff-only
sudo -u inventarios /opt/apps/inventarios-uno-a-uno/.venv/bin/pip install -r /opt/apps/inventarios-uno-a-uno/requirements.txt
cd /opt/apps/inventarios-uno-a-uno
sudo -u inventarios env APP_ENV=testing AUTH_ENABLED=false FLASK_DEBUG=false .venv/bin/python -B -m pytest -q -p no:cacheprovider
sudo -u inventarios .venv/bin/python -m pip check
```

Continuar solo si instalación y pruebas pasan. Repetir la carga Gunicorn con `--check-config` del apartado 8 usando el EnvironmentFile real. Si cambió el unit, revisarlo/copiarlo y hacer daemon-reload; si cambió el vhost, revisar el diff y validar antes de recargar. Después:

```bash
sudo systemctl start inventarios-uno-a-uno
curl -i http://127.0.0.1:8000/healthz
curl -i https://inventariospdv-v2.calcoweb.net/healthz
sudo systemctl status inventarios-uno-a-uno --no-pager
```

Restaurar el nuevo enlace Woody tras aceptar acceso y lectura. Si la actualización falla, mantener el servicio detenido y usar el rollback anterior. Para volver al código previo, verificar checkout limpio y recuperar conscientemente el SHA anotado mediante `git switch --detach SHA_PREVIO`, reinstalar sus dependencias y comprobar compatibilidad/configuración antes de reiniciar; no usar `reset --hard` sobre cambios desconocidos. Antes del próximo `pull --ff-only`, volver a la rama de despliegue identificada.

## Alcance de la preparación local

Se conservan reglas, almacenamiento y funciones de inventario. No se escribió en Google ni se desplegó Apps Script, WordPress, GCP, systemd o Apache. No se generó configuración Nginx. Ningún servidor Flask/Gunicorn fue iniciado por el agente. Las pruebas usan Flask test client y relojes simulados; la validación de certificados, DNS, Apache y el arranque real de Gunicorn debe hacerse manualmente en Debian según esta guía.

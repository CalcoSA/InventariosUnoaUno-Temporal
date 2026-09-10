# GCP: Docker Compose detrás del Apache existente

## Arquitectura y requisitos

Una VM Linux AMD64 ejecuta **un contenedor** con Gunicorn (1 worker, 4 hilos), escuchando en `127.0.0.1:8000`. Apache permanece instalado en la VM y publica HTTPS. Compose usa `network_mode: host` para que el proxy local siga siendo el único salto confiable para Flask. No publique el puerto 8000 en el firewall ni agregue `ports:`. Este archivo está destinado a Linux, según el [modo host de Docker](https://docs.docker.com/engine/network/drivers/host/).

La preparación supone Debian 12/13, como la VM prevista `calco-feplanb`; confirme el sistema real y `uname -m` (`x86_64`). Se necesitan Docker Engine, plugin Docker Compose **>= 2.30** (por `env_file.format: raw`), Python 3, gzip, util-linux, sudo y Apache con certificado válido. Si ya existe Docker u otras aplicaciones, conserve sus contenedores y configuración. No ejecute limpiezas globales ni modifique `/opt/apps/deliveryTraceability`.

```bash
hostname
cat /etc/os-release
uname -m
sudo docker version
sudo docker compose version
sudo apachectl -S
sudo ss -lntp
df -h /var/lib
```

En una VM nueva sin Docker, instálelo con el [repositorio apt oficial para Debian](https://docs.docker.com/engine/install/debian/), incluyendo `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin` y `docker-compose-plugin`. No sustituya una instalación que ya atiende otras aplicaciones sin planificar su mantenimiento. Instale además `python3 gzip util-linux sudo curl apache2` si faltan. El único servicio systemd necesario para los contenedores es el propio Docker Engine; ya no se instala una unidad Gunicorn de este proyecto.

En GCP: asigne IP estable/DNS al dominio, permita HTTPS desde las redes de usuarios y permita SSH **solo desde el runner y administradores autorizados**. Los runners públicos de GitHub no tienen una única IP fija; si su firewall requiere un origen fijo o la VM es privada, use un runner Linux propio en una red autorizada y configure `GCP_DEPLOY_RUNNER`. Este workflow utiliza SSH directo, no un túnel IAP. No deshabilite OS Login si lo exige su organización; el administrador debe preparar una identidad SSH de automatización compatible. La VM necesita salida HTTPS hacia OAuth y APIs de Google.

## 1. Copiar los dos archivos operativos

Transfiera desde el repositorio revisado `compose.yaml` y `scripts/docker_release.sh` a una carpeta temporal del usuario administrador en la VM (por ejemplo con `scp`). Desde esa carpeta, instale:

```bash
sudo install -d -o root -g root -m 0755 /opt/apps/inventarios-uno-a-uno
sudo install -d -o root -g root -m 0700 /etc/inventarios-uno-a-uno
sudo install -d -o root -g root -m 0700 /var/lib/inventarios-uno-a-uno-deployment
sudo install -d -o 10001 -g 10001 -m 0700 /var/lib/inventarios-uno-a-uno
sudo install -o root -g root -m 0644 compose.yaml /opt/apps/inventarios-uno-a-uno/compose.yaml
sudo install -o root -g root -m 0755 docker_release.sh /usr/local/sbin/inventarios-docker-release
sudo bash -n /usr/local/sbin/inventarios-docker-release
```

Si transfirió el directorio `scripts` completo, use `scripts/docker_release.sh` como origen del último `install`. `/opt`, `/opt/apps` y el directorio de esta aplicación deben ser de root y no escribibles por grupo/otros; el ejecutor verifica esto. Revise permisos sin aplicar cambios recursivos a carpetas de otras aplicaciones. Si el esquema anterior ya ocupaba esta ruta, haga copia de su configuración y ajuste únicamente este directorio de inventarios antes de continuar.

Estos dos archivos son configuración administrada de la VM. Reinstálelos cuando cambien en Git. El usuario CI no puede modificarlos; recibe solamente permiso para el ejecutor de despliegue.

## 2. Archivos privados y persistencia

Coloque, mediante una transferencia privada, los archivos de la instalación que ya funciona:

| Ruta en GCP | Contenido y permisos |
|---|---|
| `/etc/inventarios-uno-a-uno/credentials.json` | Cliente OAuth existente; `root:10001`, modo `0440`; montaje de solo lectura |
| `/etc/inventarios-uno-a-uno/sso_public.pem` | Clave pública correspondiente a WordPress; `root:10001`, modo `0440`; montaje de solo lectura |
| `/var/lib/inventarios-uno-a-uno/token.json` | Token OAuth autorizado existente; `10001:10001`, modo `0600`; carpeta escribible para renovación atómica |
| `/etc/inventarios-uno-a-uno/inventarios.env` | Variables y secreto de sesión; `root:root`, modo `0600`; Compose lo lee como root |

El ID 10001 es el usuario del contenedor. La carpeta padre `/etc/inventarios-uno-a-uno` del host puede permanecer 0700: Docker monta individualmente los archivos, no esa carpeta. El directorio del token se monta completo para permitir renombrar el archivo durante su renovación. No monte únicamente el archivo `token.json`.

Ejemplo de instalación desde archivos previamente transferidos, sin regenerar ni mostrar su contenido:

```bash
sudo install -o root -g 10001 -m 0440 credentials.json /etc/inventarios-uno-a-uno/credentials.json
sudo install -o root -g 10001 -m 0440 sso_public.pem /etc/inventarios-uno-a-uno/sso_public.pem
sudo install -o 10001 -g 10001 -m 0600 token.json /var/lib/inventarios-uno-a-uno/token.json
sudoedit /etc/inventarios-uno-a-uno/inventarios.env
sudo chown root:root /etc/inventarios-uno-a-uno/inventarios.env
sudo chmod 0600 /etc/inventarios-uno-a-uno/inventarios.env
```

Contenido de `inventarios.env` (reemplace la URL de intranet; no use comillas alrededor de valores porque el formato es `raw`):

```dotenv
SSO_ISSUER=calco-intranet
SSO_AUDIENCE=inventarios-uno-a-uno
SSO_TOKEN_MAX_AGE_SECONDS=60
SSO_CLOCK_SKEW_SECONDS=10
SESSION_JWT_ISSUER=inventarios-uno-a-uno
SESSION_JWT_AUDIENCE=inventarios-session
SESSION_JWT_COOKIE_NAME=inventario_session
SESSION_IDLE_TIMEOUT_SECONDS=1200
INTRANET_URL=https://DOMINIO-REAL-INTRANET/PAGINA-DEL-BOTON/
GOOGLE_MASTER_SPREADSHEET_ID=1q34wHfO08PDclMA2zSNf03naVkSllG6lCRcHu6dGdg4
GOOGLE_GENERAL_SUMMARY_SPREADSHEET_ID=1_Kj9mXyd5q8y1wx6D0sSmbapiGugvxj3yBo437xQk8M
APP_TIMEZONE=America/Bogota
GOOGLE_HTTP_TIMEOUT=60
GOOGLE_FORMS_COMPAT_SCRIPT_ID=
```

Genere una vez el secreto de sesión y agréguelo **sin imprimirlo**. Este comando falla si la variable ya existe; conserve el secreto entre despliegues:

```bash
sudo python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('/etc/inventarios-uno-a-uno/inventarios.env')
text = p.read_text()
assert not any(line.strip().startswith('SESSION_JWT_SECRET=') for line in text.splitlines()), 'El secreto ya existe; no se modifica'
with p.open('a') as f:
    f.write('\nSESSION_JWT_SECRET=' + secrets.token_hex(32) + '\n')
PY
```

Compose impone modo producción, autenticación activa, cookies Secure y rutas de archivos, independientemente del archivo de variables. El secreto de sesión es diferente de la clave RSA. Nunca copie la privada RSA de WordPress a GCP. Si WordPress está en esta misma VM, manténgala fuera de los montajes del contenedor.

`GOOGLE_FORMS_COMPAT_SCRIPT_ID` solo se completa si utiliza el adaptador FormApp: siga [compat/README.md](../compat/README.md) y conserve los scopes y despliegue autorizados. No reemplace el cliente OAuth por una Service Account ni regenere tokens como parte del CI/CD. Si aún no existe token, autorícelo en una estación con navegador siguiendo el README y transfiera el archivo resultante.

## 3. Apache y HTTPS

Revise los VirtualHosts existentes antes de editar. Para este dominio, configure el proxy hacia el contenedor local. Sustituya las dos rutas de certificado por las reales verificadas. Este contenido se instala en `/etc/apache2/sites-available/apache-inventariospdv-v2.conf`; si el host ya tiene ese dominio configurado, actualice su VirtualHost existente en lugar de crear uno duplicado.

```apache
<VirtualHost *:80>
    ServerName inventariospdv-v2.calcoweb.net
    RewriteEngine On
    RewriteRule ^ https://inventariospdv-v2.calcoweb.net%{REQUEST_URI} [R=308,L,NE]
</VirtualHost>

<VirtualHost *:443>
    ServerName inventariospdv-v2.calcoweb.net
    SSLEngine on
    SSLCertificateFile /RUTA/REAL/VERIFICADA/fullchain.pem
    SSLCertificateKeyFile /RUTA/REAL/VERIFICADA/privkey.pem
    ProxyRequests Off
    ProxyPreserveHost On
    ProxyAddHeaders On
    RequestHeader unset X-Forwarded-For
    RequestHeader unset X-Forwarded-Host
    RequestHeader unset X-Forwarded-Port
    RequestHeader unset Forwarded
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass / http://127.0.0.1:8000/ connectiontimeout=5 timeout=380
    ProxyPassReverse / http://127.0.0.1:8000/
    LogFormat "%h %l %u %t \"%m %U %H\" %>s %b" inventarios_safe
    CustomLog ${APACHE_LOG_DIR}/inventariospdv-v2-access.log inventarios_safe
    ErrorLog ${APACHE_LOG_DIR}/inventariospdv-v2-error.log
</VirtualHost>
```

```bash
sudo a2enmod ssl proxy proxy_http headers rewrite
sudo a2ensite apache-inventariospdv-v2.conf
sudo apachectl configtest
# Solo después de obtener Syntax OK:
sudo systemctl reload apache2
```

No cambie otros VirtualHosts. Hasta el primer despliegue, este dominio puede devolver 503 porque no hay backend. El proxy no registra query strings, cookies ni cuerpos del POST SSO. Compruebe que no exista una herramienta adicional que los registre.

## 4. Cuenta SSH para GitHub

En una VM que utilice cuentas SSH locales, cree una cuenta dedicada si no existe:

```bash
sudo adduser --disabled-password --gecos '' inventarios-deploy
sudo install -d -o inventarios-deploy -g inventarios-deploy -m 0700 /home/inventarios-deploy/.ssh
sudoedit /home/inventarios-deploy/.ssh/authorized_keys
sudo chown inventarios-deploy:inventarios-deploy /home/inventarios-deploy/.ssh/authorized_keys
sudo chmod 0600 /home/inventarios-deploy/.ssh/authorized_keys
```

En `authorized_keys`, pegue la **pública SSH de GitHub**, precedida de `restrict `, por ejemplo `restrict ssh-ed25519 AAAA... github-inventarios`. No agregue este usuario al grupo `docker` ni al grupo `sudo`. En instalaciones con OS Login, use la identidad preparada por su administrador en lugar de estos comandos de cuenta local.

Abra `sudo visudo -f /etc/sudoers.d/inventarios-docker` y agregue (cambie el usuario si corresponde):

```sudoers
inventarios-deploy ALL=(root) NOPASSWD: /usr/local/sbin/inventarios-docker-release
```

```bash
sudo chmod 0440 /etc/sudoers.d/inventarios-docker
sudo visudo -cf /etc/sudoers.d/inventarios-docker
sudo -l -U inventarios-deploy
```

El ejecutor acepta exactamente un SHA de Git, un ID de imagen y una imagen comprimida por stdin. Verifica rutas controladas por root, etiqueta e ID de la imagen, serializa despliegues con `flock` y opera únicamente sobre el proyecto Compose de inventarios. La cuenta CI puede reemplazar la aplicación y por ello tiene acceso efectivo a sus datos: limite quién puede modificar la rama/workflow de producción.

## 5. Primera puesta en marcha

Configure los [secrets y variables de GitHub](GITHUB_ACTIONS.md), luego active el despliegue. Si se llegó a instalar la unidad anterior `inventarios-uno-a-uno.service`, revise que corresponda a esta aplicación, deténgala y deshabilítela antes del primer despliegue Docker. Espere 320 segundos desde su parada para agotar JWT SSO previos. No detenga otros servicios. El puerto 8000 debe estar libre.

GitHub construye la imagen y la envía; la VM no necesita descargarla de un registro. El primer despliegue crea `/etc/inventarios-uno-a-uno/image.env` con la etiqueta de la imagen saludable. No cree este archivo con una etiqueta ficticia.

Verifique desde la VM, después del workflow:

```bash
sudo docker compose --env-file /etc/inventarios-uno-a-uno/image.env -f /opt/apps/inventarios-uno-a-uno/compose.yaml ps
curl --fail http://127.0.0.1:8000/healthz
curl --fail https://inventariospdv-v2.calcoweb.net/healthz
sudo ss -lntp 'sport = :8000'
```

Debe responder `{"status":"ok"}` y escuchar en loopback. `/healthz` comprueba el proceso/configuración, **no valida acceso a Google**. Complete la prueba de acceso desde WordPress y una lectura de inventario. Para verificar Google desde el contenedor sin un servidor adicional, ejecute conscientemente:

```bash
sudo docker compose --env-file /etc/inventarios-uno-a-uno/image.env -f /opt/apps/inventarios-uno-a-uno/compose.yaml run --rm --no-deps --entrypoint python app scripts/verify_google_access.py
```

Use ese verificador solo con token ya autorizado; su renovación puede actualizar el token persistente. Los comandos administrativos de creación/actualización de inventarios escriben en Google: no forman parte del despliegue. Si se ejecutan, use `compose run` de este mismo proyecto para compartir el volumen de bloqueos; no arranque otra instancia con locks separados.

## 6. Actualizaciones, recuperación y respaldos

El script comprueba configuración con el test client, detiene el contenedor anterior, espera **320 segundos** y arranca el nuevo con `up --wait`. La espera cubre el máximo SSO permitido (300 s + 20 s de tolerancia) porque la caché de JWT usados está en memoria. También espera antes de recuperar una imagen anterior tras un fallo. El arranque puede añadir hasta 120 segundos y el cierre de solicitudes hasta 330. No escale workers/réplicas: para despliegues sin esta pausa se requiere primero una caché de uso único compartida y persistente.

Una recuperación automática restaura la imagen, no cambios hechos en Google por usuarios. Si falla, deja la aplicación detenida y el workflow rojo. El chequeo HTTPS posterior no provoca rollback automático. Conserve respaldos privados de `inventarios.env`, claves y token; el volumen `inventarios-uno-a-uno_inventory-locks` y la carpeta de token sobreviven a reemplazos. No ejecute `down -v` ni `docker system prune --volumes`.

Para una recuperación manual tras un despliegue saludable que resulte funcionalmente incorrecto, conserve `previous-image.env` y las imágenes previas. El método preferido es revertir el commit y dejar que CI lo despliegue. Si CI no está disponible, un administrador puede usar el ejecutor con una imagen anterior que siga presente:

```bash
sudo -i
old_ref=$(sed -n 's/^INVENTARIOS_IMAGE=//p' /etc/inventarios-uno-a-uno/previous-image.env)
old_id=$(docker image inspect --format '{{.Id}}' "$old_ref")
old_sha=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$old_ref")
docker image tag "$old_id" "inventarios-uno-a-uno:ci-$old_sha"
set -o pipefail
docker image save "inventarios-uno-a-uno:ci-$old_sha" | gzip -1 | /usr/local/sbin/inventarios-docker-release "$old_sha" "$old_id"
exit
```

El flujo vuelve a verificar configuración y aplica la pausa. Solo recupera código; si cambió Compose o secretos, restaure primero la configuración compatible. La primera instalación aún no tiene una imagen anterior. Las imágenes se conservan para recuperación: vigile el espacio y retire de forma selectiva imágenes antiguas de inventarios una vez revisadas, conservando la actual y la anterior.

`restart: unless-stopped` recupera el proceso después de un reinicio de Docker/VM, pero un reinicio inesperado pierde la caché SSO sin la pausa del ejecutor. La protección de uso único está limitada a la vida del worker. La cookie sigue protegida por firma y expiración; para garantizar uso único incluso ante caídas se necesita almacenamiento compartido persistente de los `jti`. Esta configuración no modifica esa arquitectura de autenticación existente.

# GitHub: CI/CD automático a Docker en GCP

El workflow [ci-cd-gcp.yml](../.github/workflows/ci-cd-gcp.yml) ejecuta pruebas en cada push y PR. Después de un push a la rama de despliegue, construye una imagen Linux AMD64, comprueba `/healthz` sin abrir puertos, la comprime y la envía por SSH a la VM. Allí se verifica su ID y commit antes de iniciar Docker Compose. No requiere Artifact Registry, Docker Hub, clave JSON de GCP ni que la VM clone GitHub.

## 1. Preparar antes de activar

Complete [GCP](GCP_DOCKER.md) y [WordPress](WORDPRESS_SSO.md). Cree el environment **production** en `Settings > Environments`. Si configura revisores obligatorios, el despliegue esperará su aprobación aunque el push lo dispare automáticamente. Restrinja las ramas permitidas a la rama elegida.

En `Settings > Secrets and variables > Actions > Variables`, cree estas **Repository variables**:

| Variable | Valor |
|---|---|
| `GCP_DEPLOY_ENABLED` | `false` durante la preparación; `true` cuando esté lista la VM |
| `GCP_DEPLOY_BRANCH` | `main`, o su rama real de producción; si se omite, usa la rama predeterminada del repositorio |
| `GCP_DEPLOY_RUNNER` | Opcional. Por defecto `ubuntu-24.04`; para una VM privada use la etiqueta de un runner Linux con conectividad autorizada |
| `GCP_HEALTHCHECK_URL` | `https://inventariospdv-v2.calcoweb.net/healthz` |

Un runner propio debe tener Docker Engine funcionando, Docker Compose >= 2.30, Bash, Python 3, curl, gzip y OpenSSH. Debe poder construir imágenes AMD64. No use la VM de producción como runner que ejecute código de PR no confiable.

## 2. Secrets del environment production

En `Settings > Environments > production > Environment secrets`:

| Secret | Contenido |
|---|---|
| `GCP_VM_HOST` | IP o DNS de la VM, sin `https://` ni ruta |
| `GCP_SSH_USER` | `inventarios-deploy`, o usuario de OS Login preparado por el administrador |
| `GCP_SSH_PORT` | `22`, o puerto SSH real |
| `GCP_SSH_PRIVATE_KEY` | Clave privada SSH completa, con encabezado, final y saltos de línea; dedicada a esta automatización, sin passphrase |
| `GCP_SSH_KNOWN_HOSTS` | Línea de host SSH verificada, por ejemplo `IP_VM ssh-ed25519 AAAA...`; para otro puerto: `[IP_VM]:2222 ssh-ed25519 AAAA...` |

Genere el par SSH en una estación administrativa con `ssh-keygen -t ed25519 -f inventarios-github-actions -C github-inventarios`. Elija passphrase vacía para esta clave de automatización. Instale **solo la pública** en la cuenta de despliegue de la VM. Copie la privada al secret, nunca al repositorio.

Obtenga la clave pública del host por una consola GCP/SSH ya confiable: `sudo cat /etc/ssh/ssh_host_ed25519_key.pub`. Anteponer la IP/DNS usada en `GCP_VM_HOST` produce la línea de `known_hosts`. Verifique su huella con `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. No confíe ciegamente en una captura `ssh-keyscan` desde una red no verificada.

Los secretos de **la aplicación** permanecen en la VM: secreto de sesión, JSON OAuth y token Google. La clave privada RSA del SSO permanece en WordPress. No se pasan al build ni a GitHub.

## 3. Subir y activar

Suba los cambios revisados del repositorio, incluyendo `.github/`, `Dockerfile`, `compose.yaml`, `.dockerignore`, `.gitattributes`, `scripts/docker_release.sh`, `wordpress/`, pruebas, documentación y la eliminación de `deploy/`. Mantenga `.env`, `credentials/`, tokens y claves fuera de Git.

Integre estos cambios en `main` (o la rama configurada). Este workspace estaba en `InitialBranch`: un push allí ejecuta pruebas, pero no despliega si la rama configurada es `main`. No renombre ramas sin revisar su repositorio remoto.

Cuando la VM esté preparada, cambie `GCP_DEPLOY_ENABLED=true` y haga el siguiente push a la rama configurada. También puede usar `Actions > CI-CD Inventarios GCP > Run workflow`, seleccionando esa misma rama.

El pipeline prueba Python 3.11/3.12, JavaScript y el PHP real con OpenSSL; no permite pruebas omitidas en CI. Si una prueba falla, no despliega. Si falla el arranque del contenedor, el script intenta recuperar la imagen anterior. Si falla únicamente el chequeo HTTPS externo, el workflow queda rojo y debe revisarse Apache/DNS/certificado; ese paso no revierte automáticamente una imagen ya saludable.

## Qué se actualiza automáticamente

Cada despliegue publica el código de la aplicación y sus dependencias mediante una imagen nueva. `compose.yaml` y el ejecutor privilegiado se instalan inicialmente por un administrador en GCP: si los modifica después, vuelva a instalarlos siguiendo la guía de GCP **antes** del push que los necesite. WordPress se actualiza por separado. El workflow no modifica Apache, permisos ni configuración secreta.

La primera instalación no necesita pausa previa. Las actualizaciones tienen una pausa de **320 segundos**, además del cierre de solicitudes y arranque, para cubrir la caducidad máxima del JWT SSO al perderse la caché de tokens usados. No es un despliegue sin interrupción; programe los pushes de producción fuera de la captura de inventarios.

Referencia: [Secrets de GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

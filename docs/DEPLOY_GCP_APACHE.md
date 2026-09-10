# Despliegue en GCP: guía trasladada

La preparación anterior basada en una unidad systemd de Gunicorn fue sustituida por **Docker Compose**. La carpeta `deploy/` se eliminó por solicitud del proyecto. Apache permanece como proxy HTTPS en la VM.

Siga estas guías vigentes, en orden de preparación:

1. [WordPress: clave RSA, Woody o plugin y shortcode](WORDPRESS_SSO.md).
2. [GCP: Docker, archivos privados, Apache y cuenta SSH](GCP_DOCKER.md).
3. [GitHub: workflow, secrets y despliegue automático al hacer push](GITHUB_ACTIONS.md).

No instale la antigua unidad Gunicorn junto al contenedor: ambos intentarían ocupar el puerto 8000. La guía de GCP explica cómo retirar esa unidad si llegó a instalarse. Se conserva este archivo para que los enlaces anteriores sigan siendo válidos.

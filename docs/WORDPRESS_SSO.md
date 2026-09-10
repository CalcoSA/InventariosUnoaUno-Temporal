# WordPress: acceso seguro desde la intranet

**No necesita crear otro plugin si ya tiene Woody.** El archivo [wordpress/inventarios-sso.php](../wordpress/inventarios-sso.php) funciona como snippet PHP global de Woody y también incluye el encabezado para instalarse como plugin independiente. Elija una sola modalidad.

El usuario inicia sesión en WordPress. Al pulsar **INVENTARIOS PDV**, WordPress obtiene `wp_get_current_user()->user_login`, verifica sesión y nonce y firma un JWT RS256 válido por 60 segundos. El navegador lo envía por POST a `https://inventariospdv-v2.calcoweb.net/auth/sso`. Flask verifica firma, emisor, audiencia, tiempos y uso único, y entrega su cookie de sesión segura. No acepta un usuario suelto por URL o formulario como autenticación.

## 1. Preparación en el servidor de WordPress

Esta parte requiere acceso administrativo al servidor, no solo al panel WordPress. PHP debe tener OpenSSL. El usuario del proceso PHP debe poder leer la clave privada; en Debian suele ser `www-data`, pero confírmelo en su instalación, especialmente con PHP-FPM.

Ejemplo para un servidor nuevo, **sin sobrescribir claves existentes**:

```bash
sudo install -d -o root -g www-data -m 0750 /etc/calco-intranet/inventario-uno-a-uno
sudo test ! -e /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem && \
sudo sh -c 'umask 077; openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem'
sudo chown root:www-data /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem
sudo chmod 0640 /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem
sudo openssl pkey -in /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem -pubout -out /etc/calco-intranet/inventario-uno-a-uno/sso_public.pem
sudo -u www-data test -r /etc/calco-intranet/inventario-uno-a-uno/sso_private.pem
```

Si PHP usa `open_basedir`, permita esa ruta desde la configuración del hosting. Copie **solo `sso_public.pem`** a GCP, en la ruta indicada en su guía. Nunca publique la privada en WordPress Media, GitHub, la imagen Docker ni Flask. Mantenga ambos servidores con hora sincronizada.

## 2A. Con Woody existente

1. En el administrador abra Woody y cree un snippet **PHP**.
2. Copie el contenido de `wordpress/inventarios-sso.php`. Si el editor ya agrega `<?php`, omita esa primera línea.
3. Configure ejecución automática **en todas partes**, incluido `wp-admin/admin-post.php`, y actívelo. No lo configure para ejecutarse únicamente al renderizar un shortcode de Woody: los hooks del POST deben registrarse también.
4. En la página protegida de la intranet agregue un bloque Shortcode con `[inventarios_pdv_sso]`.
5. Excluya esa página de caché para usuarios autenticados. El botón genera el JWT al hacer clic, no al cargar la página.

## 2B. Sin Woody

El mismo archivo ya es un plugin mínimo. Cree una carpeta `inventarios-pdv-sso`, coloque dentro `inventarios-sso.php` y comprímala como `inventarios-pdv-sso.zip`. En WordPress: `Plugins > Añadir nuevo > Subir plugin`, cargue el ZIP y actívelo. Alternativamente, un administrador puede copiarlo a `wp-content/plugins/inventarios-pdv-sso/inventarios-sso.php` y activarlo desde el panel.

Agregue el mismo shortcode `[inventarios_pdv_sso]` a la página protegida. No active simultáneamente este plugin y el snippet de Woody. El archivo sigue el [encabezado oficial de plugins WordPress](https://developer.wordpress.org/plugins/plugin-basics/header-requirements/).

## 3. Valores coordinados y comprobación

| Dato | WordPress | GCP / Flask |
|---|---|---|
| Emisor | `calco-intranet` | `SSO_ISSUER=calco-intranet` |
| Audiencia | `inventarios-uno-a-uno` | `SSO_AUDIENCE=inventarios-uno-a-uno` |
| Duración del JWT inicial | 60 segundos por defecto | `SSO_TOKEN_MAX_AGE_SECONDS=60` |
| Claves | Privada RSA en `/etc/calco-intranet/inventario-uno-a-uno/` | Pública correspondiente en `/etc/inventarios-uno-a-uno/` |
| Destino | URL fija en PHP y en su CSP | Dominio HTTPS del Apache de GCP |

Si cambia el dominio, ajuste tanto `$destination` como `form-action` de la CSP en el PHP, el VirtualHost, DNS/certificado y `GCP_HEALTHCHECK_URL`. `INTRANET_URL` en GCP debe apuntar a la página real que contiene el botón; no es la URL de inventarios.

Pruebe con un usuario real autenticado: se abre una pestaña de inventarios; la URL no contiene tokens ni nombre de usuario. Sin sesión WordPress no aparece el botón y el endpoint de generación rechaza el acceso. Acceder directamente a inventarios no crea una sesión. La sesión de inventarios vence tras 20 minutos de inactividad; vuelva a entrar desde el botón. El borrador local se conserva. Cerrar sesión en WordPress no revoca inmediatamente una cookie de inventarios ya emitida: son sesiones separadas.

Actualmente cualquier usuario autenticado de WordPress puede generar el acceso; no se añadió una restricción por rol o área. No registre cuerpos de `/auth/sso`, cookies ni JWT en herramientas de depuración o analítica. Esta identidad WordPress es independiente de la cuenta OAuth con la que el backend accede a Google Sheets/Drive/Forms.

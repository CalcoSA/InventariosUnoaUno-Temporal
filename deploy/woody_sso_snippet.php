<?php
/**
 * Woody: PHP snippet, auto-execute EVERYWHERE (including wp-admin/admin-post).
 * Then place [inventarios_pdv_sso] on the protected intranet page.
 * If Woody supplies <?php automatically, omit this file's opening PHP tag.
 * No Composer. Do not cache this shortcode page for logged-in users.
 */
if (!defined('ABSPATH')) {
    exit;
}

add_shortcode('inventarios_pdv_sso', static function () {
    if (!is_user_logged_in()) {
        return '';
    }
    // Open ONE new tab. Generate the short-lived JWT only after the click.
    return '<form method="post" target="_blank" rel="noopener noreferrer" action="'
        . esc_url(admin_url('admin-post.php')) . '" style="text-align:center">'
        . '<input type="hidden" name="action" value="inventarios_pdv_sso">'
        . wp_nonce_field('inventarios_pdv_sso', '_wpnonce', true, false)
        . '<button type="submit" style="font-size:1.5em;cursor:pointer">INVENTARIOS PDV</button>'
        . '</form>';
});

add_action('admin_post_nopriv_inventarios_pdv_sso', static function () {
    wp_die('Ingrese nuevamente desde la intranet.', 'Acceso requerido', ['response' => 401]);
});

add_action('admin_post_inventarios_pdv_sso', static function () {
    if (!is_user_logged_in() || ($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
        wp_die('Acceso requerido.', 'Inventarios PDV', ['response' => 401]);
    }
    check_admin_referer('inventarios_pdv_sso');
    nocache_headers();
    header('Cache-Control: no-store, private, max-age=0');
    header('Referrer-Policy: no-referrer');
    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    $destination = 'https://inventariospdv-v2.calcoweb.net/auth/sso';
    $keyPath = '/etc/calco-intranet/inventario-uno-a-uno/sso_private.pem';
    // Optional constants in WordPress wp-config.php; never put the private key there.
    $ttl = defined('INVENTARIOS_SSO_TTL_SECONDS') ? (int) INVENTARIOS_SSO_TTL_SECONDS : 60;
    try {
        if ($ttl < 1 || $ttl > 300 || !is_readable($keyPath)) {
            throw new RuntimeException('SSO no configurado');
        }
        $subject = wp_get_current_user()->user_login;
        if (!is_string($subject) || trim($subject) === '') {
            throw new RuntimeException('Usuario no válido');
        }
        $pem = @file_get_contents($keyPath);
        $privateKey = $pem === false ? false : @openssl_pkey_get_private($pem);
        unset($pem);
        $details = $privateKey === false ? false : openssl_pkey_get_details($privateKey);
        if (!$details || $details['type'] !== OPENSSL_KEYTYPE_RSA || $details['bits'] < 2048) {
            throw new RuntimeException('Clave no válida');
        }
        $base64url = static function ($bytes) {
            return rtrim(strtr(base64_encode($bytes), '+/', '-_'), '=');
        };
        $now = time();
        $claims = ['iss' => 'calco-intranet', 'aud' => 'inventarios-uno-a-uno',
            'sub' => $subject, 'iat' => $now, 'nbf' => $now, 'exp' => $now + $ttl,
            'jti' => bin2hex(random_bytes(32))];
        $unsigned = $base64url(json_encode(['alg' => 'RS256', 'typ' => 'JWT'], JSON_THROW_ON_ERROR))
            . '.' . $base64url(json_encode($claims, JSON_THROW_ON_ERROR));
        if (!openssl_sign($unsigned, $signature, $privateKey, OPENSSL_ALGO_SHA256)) {
            throw new RuntimeException('Firma no disponible');
        }
        unset($privateKey, $details);
        $token = $unsigned . '.' . $base64url($signature);
        $nonce = $base64url(random_bytes(18));
    } catch (Throwable $error) {
        // Never echo/log exception details, key material or either JWT.
        wp_die('No fue posible abrir Inventarios PDV. Contacte al administrador.',
            'Acceso no disponible', ['response' => 503]);
        return;
    }
    header("Content-Security-Policy: default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action https://inventariospdv-v2.calcoweb.net; script-src 'nonce-" . $nonce . "'");
    // Already in the target=_blank tab. POST the hidden token in this same tab.
    // The JWT appears only in the required hidden input, never visible text or URL.
    echo '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        . '<title>Inventarios PDV</title></head><body>'
        . '<form id="inventarios-sso" method="post" target="_self" action="' . esc_url($destination) . '">'
        . '<input type="hidden" name="token" value="' . esc_attr($token) . '">'
        . '<noscript><button type="submit">INVENTARIOS PDV</button></noscript></form>'
        . '<script nonce="' . esc_attr($nonce) . '">document.getElementById("inventarios-sso").submit();</script>'
        . '</body></html>';
    exit;
});

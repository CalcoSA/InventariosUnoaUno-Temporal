<?php
/** WordPress doubles for the real snippet. No HTTP server, disk keys or Google. */
namespace WoodyTest;

$input = json_decode(\stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
$actions = [];
$shortcodes = [];
$responseHeaders = [];
\define('ABSPATH', '/test-wordpress/');
$_SERVER['REQUEST_METHOD'] = $input['method'] ?? 'POST';

function is_user_logged_in() { global $input; return $input['logged_in'] ?? true; }
function wp_get_current_user() { global $input; return (object) ['user_login' => $input['subject'] ?? 'wp.usuario']; }
function add_shortcode($name, $callback) { global $shortcodes; $shortcodes[$name] = $callback; }
function add_action($name, $callback) { global $actions; $actions[$name] = $callback; }
function admin_url($path) { return 'https://intranet.example.test/wp-admin/' . $path; }
function esc_attr($value) { return htmlspecialchars($value, ENT_QUOTES, 'UTF-8'); }
function esc_url($value) { return esc_attr($value); }
function wp_nonce_field(...$args) { return '<input type="hidden" name="_wpnonce" value="test-nonce">'; }
function check_admin_referer($action) {
    global $input;
    if (!($input['nonce_valid'] ?? true)) wp_die('Nonce inválido', '', ['response' => 403]);
}
function nocache_headers() {}
function header($value) { global $responseHeaders; $responseHeaders[] = $value; }
function time() { global $input; return $input['now']; }
function is_readable($path) {
    global $input;
    return $path === '/etc/calco-intranet/inventario-uno-a-uno/sso_private.pem' && !($input['missing_key'] ?? false);
}
function file_get_contents($path) {
    global $input;
    if ($path === '/etc/calco-intranet/inventario-uno-a-uno/sso_private.pem') return $input['private_key'];
    throw new \RuntimeException('Unexpected file read in test');
}
function wp_die($message, $title = '', $options = []) {
    echo 'ACCESS DENIED ' . ($options['response'] ?? 500);
    exit;
}

ob_start();
register_shutdown_function(static function () {
    global $responseHeaders;
    $body = ob_get_clean();
    echo json_encode(['body' => $body, 'headers' => $responseHeaders], JSON_THROW_ON_ERROR);
});
$source = \file_get_contents($argv[1]);
eval('namespace WoodyTest; use \\RuntimeException; use \\Throwable;' . substr($source, 5));
if (($input['scenario'] ?? '') === 'render') {
    echo $shortcodes['inventarios_pdv_sso']();
} else {
    $actions['admin_post_inventarios_pdv_sso']();
}

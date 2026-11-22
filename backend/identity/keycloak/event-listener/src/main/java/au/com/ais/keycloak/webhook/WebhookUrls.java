package au.com.ais.keycloak.webhook;

import java.net.InetAddress;
import java.net.URI;
import java.util.Locale;

/**
 * Checks the webhook URL. The rule is the same as in oidc_verify (G-13): https only. Plain http is an
 * explicit exception for a development address: localhost, a name under ".localhost" (RFC 6761) or a
 * loopback IP literal. Over plain http to another host, user ids would travel unencrypted.
 *
 * <p>Added in this fork. Not part of the upstream project.
 */
final class WebhookUrls {

    private WebhookUrls() {
    }

    static URI check(String url) {
        URI target;
        try {
            target = URI.create(url);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("webhook URL is not valid");
        }
        String host = target.getHost();
        if (host == null || host.isEmpty()) {
            throw new IllegalArgumentException("webhook URL has no host");
        }
        if ("https".equals(target.getScheme())) {
            return target;
        }
        if ("http".equals(target.getScheme()) && isDevelopmentHost(host)) {
            return target;
        }
        throw new IllegalArgumentException("webhook URL must use https; plain http is allowed only for localhost and loopback");
    }

    private static boolean isDevelopmentHost(String host) {
        String name = host.toLowerCase(Locale.ROOT);
        if (name.endsWith(".")) name = name.substring(0, name.length() - 1);
        if (name.equals("localhost") || name.endsWith(".localhost")) return true;
        String literal = name.startsWith("[") && name.endsWith("]") ? name.substring(1, name.length() - 1) : name;
        boolean ipLiteral = literal.contains(":") || literal.matches("[0-9.]+");
        if (!ipLiteral) return false; // never resolve a name here
        try {
            return InetAddress.getByName(literal).isLoopbackAddress();
        } catch (Exception e) {
            return false;
        }
    }
}

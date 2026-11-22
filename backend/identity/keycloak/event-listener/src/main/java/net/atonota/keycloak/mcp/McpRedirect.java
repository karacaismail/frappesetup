package net.atonota.keycloak.mcp;

import java.net.URI;
import java.util.Collection;
import java.util.List;
import java.util.Locale;
import java.util.Set;

final class McpRedirect {

    private static final Set<String> LOOPBACK = Set.of("localhost", "127.0.0.1", "[::1]");

    private McpRedirect() {
    }

    static boolean matches(Set<String> registered, List<String> submitted, boolean development) {
        if (submitted == null || submitted.size() != 1 || submitted.getFirst() == null) {
            return false;
        }
        return allowsRegistration(registered, development) && registered.contains(submitted.getFirst());
    }

    static boolean allowsRegistration(Collection<String> registered, boolean development) {
        return registered != null && !registered.isEmpty()
                && registered.stream().allMatch(address -> isSecure(address, development));
    }

    private static boolean isSecure(String address, boolean development) {
        if (address == null || address.contains("*") || address.toLowerCase(Locale.ROOT).contains("%2a")) {
            return false;
        }
        URI uri;
        try {
            uri = URI.create(address);
        } catch (IllegalArgumentException error) {
            return false;
        }
        String host = uri.getHost();
        int port = uri.getPort();
        if (host == null || uri.getRawUserInfo() != null || uri.getRawFragment() != null || port == 0 || port > 65535) {
            return false;
        }
        if ("https".equalsIgnoreCase(uri.getScheme())) {
            return true;
        }
        return development && "http".equalsIgnoreCase(uri.getScheme()) && port > 0
                && LOOPBACK.contains(host.toLowerCase(Locale.ROOT));
    }
}

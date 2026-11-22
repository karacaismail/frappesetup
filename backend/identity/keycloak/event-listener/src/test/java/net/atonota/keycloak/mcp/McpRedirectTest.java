package net.atonota.keycloak.mcp;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class McpRedirectTest {

    @Test
    void requiresOneExplicitExactMatch() {
        String callback = "https://client.example.test:443/callback";
        Set<String> registered = Set.of(callback);

        assertTrue(McpRedirect.matches(registered, List.of(callback), false));
        assertFalse(McpRedirect.matches(registered, null, false));
        assertFalse(McpRedirect.matches(registered, List.of(callback, callback), false));
        assertFalse(McpRedirect.matches(registered, List.of(callback + "\n"), false));
        assertFalse(McpRedirect.matches(registered, List.of("https://client.example.test/callback"), false));
        assertFalse(McpRedirect.matches(registered, List.of(callback + "/other"), false));
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "https://client.example.test/*",
        "https://client.example.test/%2a",
        "https://user@client.example.test/callback",
        "https://client.example.test/callback#",
        "https://client.example.test/callback#fragment",
        "http://client.example.test/callback",
        "http://localhost.example.test:47312/callback",
        "http://localhost/callback",
        "http://localhost:0/callback",
        "http://localhost:65536/callback",
        "//client.example.test/callback"
    })
    void refusesUnsafeRegisteredCallbacks(String callback) {
        assertFalse(McpRedirect.matches(Set.of(callback), List.of(callback), true));
        String safe = "https://client.example.test/callback";
        assertFalse(McpRedirect.matches(Set.of(safe, callback), List.of(safe), true));
    }

    @ParameterizedTest
    @ValueSource(strings = {"localhost", "127.0.0.1", "[::1]"})
    void allowsFixedLoopbackHttpOnlyInDevelopment(String host) {
        String callback = "http://" + host + ":47312/callback";
        Set<String> registered = Set.of(callback);

        assertTrue(McpRedirect.matches(registered, List.of(callback), true));
        assertFalse(McpRedirect.matches(registered, List.of(callback), false));
        assertFalse(McpRedirect.matches(registered, List.of(callback.replace(":47312", ":47313")), true));
    }
}

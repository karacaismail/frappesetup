package au.com.ais.keycloak.webhook;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Contract section 11: plain HTTP is allowed only for an address on a fixed list. Everything else needs
 * HTTPS. The list comes from a file that only the development image carries, so the production image
 * has plain HTTP off whatever its environment says.
 */
class WebhookUrlsTest {

    private static final Set<String> NONE = Set.of();

    @Test
    void httpsIsAccepted() {
        assertDoesNotThrow(() -> WebhookUrls.check("https://identity-sync.internal.example.test/v1/events", NONE));
    }

    @Test
    void plainHttpIsRefusedWithoutAList() {
        for (String url : new String[] {"http://identity-sync:8080/v1/events", "http://localhost:8080/v1/events",
                "http://127.0.0.1:8080/v1/events", "http://event-sink.localhost:8080/v1/events"}) {
            assertThrows(IllegalArgumentException.class, () -> WebhookUrls.check(url, NONE), url);
        }
    }

    @Test
    void plainHttpIsAcceptedOnlyForAListedHost() {
        Set<String> list = Set.of("event-sink.localhost");
        assertDoesNotThrow(() -> WebhookUrls.check("http://event-sink.localhost:8080/v1/events", list));
        assertDoesNotThrow(() -> WebhookUrls.check("http://EVENT-SINK.localhost:8080/v1/events", list));
        for (String url : new String[] {"http://other.localhost:8080/v1/events", "http://127.0.0.1/v1/events",
                "http://event-sink.localhost.example.test/v1/events"}) {
            assertThrows(IllegalArgumentException.class, () -> WebhookUrls.check(url, list), url);
        }
    }

    @Test
    void otherSchemesAndBrokenUrlsAreRefused() {
        Set<String> list = Set.of("identity-sync");
        for (String url : new String[] {"ftp://identity-sync/v1/events", "identity-sync/v1/events", "https:///v1/events"}) {
            assertThrows(IllegalArgumentException.class, () -> WebhookUrls.check(url, list), url);
        }
    }

    @Test
    void missingListFileMeansNoPlainHttp(@TempDir Path dir) {
        assertEquals(NONE, WebhookUrls.loadPlainHttpHosts(dir.resolve("absent.txt")));
    }

    @Test
    void listFileIgnoresCommentsAndBlankLines(@TempDir Path dir) throws Exception {
        Path file = dir.resolve("hosts.txt");
        Files.writeString(file, "# development only\n\n  Event-Sink.localhost  \n", StandardCharsets.UTF_8);
        assertEquals(Set.of("event-sink.localhost"), WebhookUrls.loadPlainHttpHosts(file));
    }

    @Test
    void factoryReadsTheListFromAFixedPath() {
        assertEquals(Path.of("/opt/keycloak/conf/webhook-plain-http-hosts.txt"),
                WebhookEventListenerProviderFactory.PLAIN_HTTP_HOSTS_FILE);
    }
}

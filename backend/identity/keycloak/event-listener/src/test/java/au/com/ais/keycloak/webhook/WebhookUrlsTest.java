package au.com.ais.keycloak.webhook;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

/** Same rule as oidc_verify (G-13): https only; plain http only for a development address. */
class WebhookUrlsTest {

    @Test
    void httpsIsAccepted() {
        assertDoesNotThrow(() -> WebhookUrls.check("https://identity-sync.internal.example.test/v1/events"));
    }

    @Test
    void plainHttpToADevelopmentAddressIsAccepted() {
        for (String url : new String[] {"http://localhost:8080/v1/events", "http://event-sink.localhost:8080/v1/events",
                "http://127.0.0.1:8080/v1/events", "http://[::1]:8080/v1/events"}) {
            assertDoesNotThrow(() -> WebhookUrls.check(url), url);
        }
    }

    @Test
    void plainHttpToAnyOtherHostIsRefused() {
        for (String url : new String[] {"http://identity-sync:8080/v1/events", "http://10.0.0.5/v1/events",
                "http://localhost.example.test/v1/events", "ftp://identity-sync/v1/events", "identity-sync/v1/events"}) {
            assertThrows(IllegalArgumentException.class, () -> WebhookUrls.check(url), url);
        }
    }
}

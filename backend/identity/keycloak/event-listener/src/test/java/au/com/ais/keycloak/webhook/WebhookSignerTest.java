package au.com.ais.keycloak.webhook;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

/**
 * Expected values come from the identity-sync contract (webhookSignature): HMAC-SHA256 over
 * "<timestamp>.<mode>.<raw body>", header value "sha256=<hex>". The vectors were computed
 * independently with Python's hmac module, not with this code.
 */
class WebhookSignerTest {

    private static final String SECRET = "test-secret-0123456789abcdef"; // gitleaks:allow (synthetic test value)
    private static final byte[] BODY = "{\"id\":\"e1\",\"realmId\":\"r1\"}".getBytes(StandardCharsets.UTF_8);

    @Test
    void signsTimestampModeAndBody() {
        WebhookSigner signer = new WebhookSigner(SECRET);
        assertEquals("sha256=f2b645cac4297bc72e18f89026f6eec766e3ec08a374a15f7f0744cabf6c84ec",
                signer.sign(1795000000L, "execute", BODY));
    }

    @Test
    void modeIsPartOfTheSignature() {
        WebhookSigner signer = new WebhookSigner(SECRET);
        assertEquals("sha256=b6602c9136c348748fd63e99decc02783248e0f7ce19d1504c6686f84b95266b",
                signer.sign(1795000000L, "preview", BODY));
    }

    @Test
    void timestampIsPartOfTheSignature() {
        WebhookSigner signer = new WebhookSigner(SECRET);
        assertEquals("sha256=0c2e980567c37ed4dce4391b21665ae04c681daca6ce97062286570579c8a0e7",
                signer.sign(1795000001L, "execute", BODY));
        assertNotEquals(signer.sign(1795000000L, "execute", BODY), signer.sign(1795000001L, "execute", BODY));
    }

    @Test
    void rejectsUnknownMode() {
        WebhookSigner signer = new WebhookSigner(SECRET);
        assertThrows(IllegalArgumentException.class, () -> signer.sign(1795000000L, "run", BODY));
    }

    @Test
    void rejectsShortOrMissingSecret() {
        assertThrows(IllegalArgumentException.class, () -> new WebhookSigner(null));
        assertThrows(IllegalArgumentException.class, () -> new WebhookSigner(""));
        assertThrows(IllegalArgumentException.class, () -> new WebhookSigner("short-secret"));
    }

    @Test
    void headerNamesMatchTheContract() {
        assertEquals("X-Identity-Sync-Signature", WebhookSigner.SIGNATURE_HEADER);
        assertEquals("X-Identity-Sync-Timestamp", WebhookSigner.TIMESTAMP_HEADER);
    }
}

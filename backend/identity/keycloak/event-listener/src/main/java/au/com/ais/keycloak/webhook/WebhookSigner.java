package au.com.ais.keycloak.webhook;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * Signs a webhook request the way the identity-sync contract asks (webhookSignature).
 *
 * <p>The signed content is {@code <timestamp>.<mode>.<raw body>}. The timestamp is Unix seconds.
 * The mode is {@code execute} or {@code preview}. The header value is {@code sha256=<hex>}.
 *
 * <p>Added in this fork. Not part of the upstream project.
 */
final class WebhookSigner {

    static final String SIGNATURE_HEADER = "X-Identity-Sync-Signature";
    static final String TIMESTAMP_HEADER = "X-Identity-Sync-Timestamp";
    static final String MODE_EXECUTE = "execute";
    static final String MODE_PREVIEW = "preview";
    static final int MIN_SECRET_LENGTH = 16;

    private static final Set<String> MODES = Set.of(MODE_EXECUTE, MODE_PREVIEW);
    private static final String ALGORITHM = "HmacSHA256";

    private final SecretKeySpec key;

    WebhookSigner(String secret) {
        if (secret == null || secret.length() < MIN_SECRET_LENGTH) {
            throw new IllegalArgumentException("webhook secret must have at least " + MIN_SECRET_LENGTH + " characters");
        }
        this.key = new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), ALGORITHM);
    }

    String sign(long timestampSeconds, String mode, byte[] body) {
        if (!MODES.contains(mode)) {
            throw new IllegalArgumentException("unknown mode");
        }
        try {
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(key);
            mac.update((timestampSeconds + "." + mode + ".").getBytes(StandardCharsets.US_ASCII));
            return "sha256=" + HexFormat.of().formatHex(mac.doFinal(body));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);
        }
    }
}

/*
 * Added by Atonota for G-162 (24 November 2026). Not part of cloudflightio/keycloak-magic-link.
 * Licensed under the Apache License, Version 2.0, like the extension it extends.
 * Design: backend/docs/decisions/0003-keycloak-extensions.md, section "G-162".
 */
package io.cloudflight.keycloak.magiclink.sending;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;

import org.jboss.logging.Logger;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.utils.KeycloakModelUtils;

/**
 * Limits how many magic link mails go to one address in a sliding window.
 *
 * <p>Each address has {@code limit} slots in Keycloak's single use object store. A slot is taken with
 * {@code putIfAbsent(slot, window)} and frees itself after {@code window} seconds. When every slot is
 * taken, no mail is sent. So in any window at most {@code limit} mails go to one address, also when
 * requests arrive at the same time. Each slot is tried in its own transaction: a store that only
 * checks the key at commit (the JPA store) then refuses one of two racing requests instead of both.
 *
 * <p>The key holds the realm id and the SHA-256 digest of the lower case address. The store never
 * holds the plain address.
 */
public final class MagicLinkSendLimiter {

    /** Configuration key: how many mails one address may receive in a window. */
    public static final String LIMIT_CONFIG_KEY = "magiclink.send.limit";
    /** Configuration key: the window length in seconds. */
    public static final String WINDOW_CONFIG_KEY = "magiclink.send.window.seconds";
    public static final int DEFAULT_LIMIT = 3;
    public static final long DEFAULT_WINDOW_SECONDS = 900L;

    private static final String KEY_PREFIX = "magiclink-send:";
    private static final Logger logger = Logger.getLogger(MagicLinkSendLimiter.class);

    private final int limit;
    private final long windowSeconds;

    public MagicLinkSendLimiter(int limit, long windowSeconds) {
        this.limit = limit;
        this.windowSeconds = windowSeconds;
    }

    /** Reads the limit and the window from the authenticator configuration. Missing or bad values use the defaults. */
    public static MagicLinkSendLimiter fromConfig(Map<String, String> config) {
        int limit = DEFAULT_LIMIT;
        long window = DEFAULT_WINDOW_SECONDS;
        if (config != null) {
            limit = (int) positive(config.get(LIMIT_CONFIG_KEY), DEFAULT_LIMIT);
            window = positive(config.get(WINDOW_CONFIG_KEY), DEFAULT_WINDOW_SECONDS);
        }
        return new MagicLinkSendLimiter(limit, window);
    }

    /**
     * Takes a free slot for the address. Returns false when all slots are taken or the store fails;
     * then the caller must not send a mail.
     */
    public boolean tryAcquire(KeycloakSessionFactory factory, String realmId, String address) {
        final String base = KEY_PREFIX + realmId + ":" + digest(address) + ":";
        for (int slot = 1; slot <= limit; slot++) {
            final String key = base + slot;
            try {
                Boolean taken = KeycloakModelUtils.runJobInTransactionWithResult(factory,
                      session -> session.singleUseObjects().putIfAbsent(key, windowSeconds));
                if (Boolean.TRUE.equals(taken)) {
                    return true;
                }
            } catch (RuntimeException e) {
                // A racing request took this slot first. Try the next one. The key holds no address.
                logger.debugf("Magic link send slot %d not taken: %s", slot, e.getClass().getSimpleName());
            }
        }
        return false;
    }

    static String digest(String address) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                  .digest(address.trim().toLowerCase(Locale.ROOT).getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is missing", e);
        }
    }

    private static long positive(String value, long fallback) {
        if (value == null) {
            return fallback;
        }
        try {
            long parsed = Long.parseLong(value.trim());
            return parsed > 0 && parsed <= Integer.MAX_VALUE ? parsed : fallback;
        } catch (NumberFormatException e) {
            return fallback;
        }
    }
}

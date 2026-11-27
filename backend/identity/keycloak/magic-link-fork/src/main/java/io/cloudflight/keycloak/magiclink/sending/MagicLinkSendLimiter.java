/*
 * Added by Atonota for G-162 (24 November 2026). Not part of cloudflightio/keycloak-magic-link.
 * Licensed under the Apache License, Version 2.0, like the extension it extends.
 * Design: backend/docs/decisions/0003-keycloak-extensions.md, the "G-162" section and the "G-162 follow-up work" section.
 */
package io.cloudflight.keycloak.magiclink.sending;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

import org.jboss.logging.Logger;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.utils.KeycloakModelUtils;

/**
 * Limits how many magic link mails go out, per address and per source.
 *
 * <p>A counter has {@code n} slots in Keycloak's single use object store. A slot is taken with
 * {@code putIfAbsent(slot, window)} and frees itself after {@code window} seconds. When every slot is
 * taken, no mail is sent. Each slot is tried in its own transaction: a store that only checks the key
 * at commit (the JPA store) then refuses one of two racing requests instead of both.
 *
 * <p>Three counters share the window:
 * <ul>
 * <li>Address limit: at most {@code limit} mails to one address.</li>
 * <li>Source share: one source takes at most {@code sourceShare} of those slots. The share is below
 * the address limit, so one source cannot use up another person's mails.</li>
 * <li>Source ceiling: one source asks for at most {@code sourceRequestLimit} links, for any address,
 * also an unknown one.</li>
 * </ul>
 * A source is the client IP address: an IPv4 address, or the first 64 bits of an IPv6 address.
 * Private, loopback and link local addresses are no source: many people can hide behind them (on the
 * server today every IPv6 client arrives from the Docker gateway). Then only the address limit applies.
 *
 * <p>Keys hold the realm id and SHA-256 digests. The store never holds a plain address or IP.
 * The queue ceiling counts the mail jobs that wait or run on this node.
 */
public final class MagicLinkSendLimiter {

    /** Configuration key: how many mails one address may receive in a window. */
    public static final String LIMIT_CONFIG_KEY = "magiclink.send.limit";
    /** Configuration key: the window length in seconds. */
    public static final String WINDOW_CONFIG_KEY = "magiclink.send.window.seconds";
    /** Configuration key: how many of one address's slots one source may take. */
    public static final String SOURCE_SHARE_CONFIG_KEY = "magiclink.send.source.share";
    /** Configuration key: how many link requests one source may make in a window. */
    public static final String SOURCE_REQUEST_LIMIT_CONFIG_KEY = "magiclink.request.source.limit";
    /** Configuration key: how many mail jobs may wait at once on one node. */
    public static final String QUEUE_MAX_CONFIG_KEY = "magiclink.send.queue.max";
    public static final int DEFAULT_LIMIT = 3;
    public static final long DEFAULT_WINDOW_SECONDS = 900L;
    public static final int DEFAULT_SOURCE_SHARE = 2;
    public static final int DEFAULT_SOURCE_REQUEST_LIMIT = 20;
    public static final int DEFAULT_QUEUE_MAX = 1000;

    private static final String KEY_PREFIX = "magiclink-send:";
    private static final String SOURCE_SHARE_PREFIX = "magiclink-send-src:";
    private static final String SOURCE_REQUEST_PREFIX = "magiclink-req:";
    private static final Pattern IPV4 = Pattern.compile("(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})");
    private static final Pattern IPV6 = Pattern.compile("[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*");
    /** Mail jobs that wait or run on this node. Keycloak's executor queue itself has no bound. */
    private static final AtomicInteger PENDING = new AtomicInteger();
    private static final Logger logger = Logger.getLogger(MagicLinkSendLimiter.class);

    private final int limit;
    private final long windowSeconds;
    private final int sourceShare;
    private final int sourceRequestLimit;
    private final int queueMax;

    /** The source share is cut to {@code limit - 1} (at least 1), so a share never covers every slot. */
    public MagicLinkSendLimiter(int limit, long windowSeconds, int sourceShare, int sourceRequestLimit, int queueMax) {
        this.limit = limit;
        this.windowSeconds = windowSeconds;
        this.sourceShare = Math.min(sourceShare, Math.max(1, limit - 1));
        this.sourceRequestLimit = sourceRequestLimit;
        this.queueMax = queueMax;
    }

    /** Reads the limits from the authenticator configuration. Missing or bad values use the defaults. */
    public static MagicLinkSendLimiter fromConfig(Map<String, String> config) {
        if (config == null) {
            return new MagicLinkSendLimiter(DEFAULT_LIMIT, DEFAULT_WINDOW_SECONDS, DEFAULT_SOURCE_SHARE,
                  DEFAULT_SOURCE_REQUEST_LIMIT, DEFAULT_QUEUE_MAX);
        }
        return new MagicLinkSendLimiter(
              (int) positive(config.get(LIMIT_CONFIG_KEY), DEFAULT_LIMIT),
              positive(config.get(WINDOW_CONFIG_KEY), DEFAULT_WINDOW_SECONDS),
              (int) positive(config.get(SOURCE_SHARE_CONFIG_KEY), DEFAULT_SOURCE_SHARE),
              (int) positive(config.get(SOURCE_REQUEST_LIMIT_CONFIG_KEY), DEFAULT_SOURCE_REQUEST_LIMIT),
              (int) positive(config.get(QUEUE_MAX_CONFIG_KEY), DEFAULT_QUEUE_MAX));
    }

    /**
     * Takes a free slot for the address. Returns false when all slots are taken or the store fails;
     * then the caller must not send a mail.
     */
    public boolean tryAcquire(KeycloakSessionFactory factory, String realmId, String address) {
        return takeSlot(factory, KEY_PREFIX + realmId + ":" + digest(address) + ":", limit);
    }

    /** Takes a slot of the source's share of this address. Call it before {@link #tryAcquire}. */
    public boolean tryAcquireSourceShare(KeycloakSessionFactory factory, String realmId, String address, String source) {
        return takeSlot(factory, SOURCE_SHARE_PREFIX + realmId + ":" + digest(address) + ":" + digest(source) + ":",
              sourceShare);
    }

    /** Takes a slot of the source's request ceiling. Unknown addresses count too. */
    public boolean tryAcquireSourceRequest(KeycloakSessionFactory factory, String realmId, String source) {
        return takeSlot(factory, SOURCE_REQUEST_PREFIX + realmId + ":" + digest(source) + ":", sourceRequestLimit);
    }

    /** Counts one more waiting mail job. Returns false at the queue ceiling; then the job is not queued. */
    public boolean tryEnterQueue() {
        while (true) {
            int pending = PENDING.get();
            if (pending >= queueMax) {
                return false;
            }
            if (PENDING.compareAndSet(pending, pending + 1)) {
                return true;
            }
        }
    }

    /** Counts one waiting mail job less. Call it once for every {@link #tryEnterQueue} that returned true. */
    public void leaveQueue() {
        PENDING.decrementAndGet();
    }

    /**
     * Returns the source of a client address, or null when the address is no source.
     *
     * <p>The value comes from {@code ClientConnection.getRemoteAddr()}. Keycloak takes it from
     * X-Forwarded-For (KC_PROXY_HEADERS=xforwarded). Only Caddy reaches Keycloak, and Caddy writes
     * that header itself. Only literal addresses are read: a host name is never looked up.
     */
    public static String sourceOf(String remoteAddress) {
        if (remoteAddress == null) {
            return null;
        }
        String value = remoteAddress.trim();
        if (value.startsWith("[") && value.endsWith("]")) {
            value = value.substring(1, value.length() - 1);
        }
        int zone = value.indexOf('%');
        if (zone >= 0) {
            value = value.substring(0, zone);
        }
        InetAddress address = literal(value);
        if (address == null || address.isAnyLocalAddress() || address.isLoopbackAddress()
              || address.isLinkLocalAddress() || address.isSiteLocalAddress() || address.isMulticastAddress()) {
            return null;
        }
        if (address instanceof Inet4Address) {
            return address.getHostAddress();
        }
        byte[] bytes = address.getAddress();
        if ((bytes[0] & 0xfe) == 0xfc) {
            // fc00::/7, unique local addresses.
            return null;
        }
        return HexFormat.of().formatHex(bytes, 0, 8) + "::/64";
    }

    private static InetAddress literal(String value) {
        try {
            var ipv4 = IPV4.matcher(value);
            if (ipv4.matches()) {
                byte[] bytes = new byte[4];
                for (int i = 0; i < 4; i++) {
                    int part = Integer.parseInt(ipv4.group(i + 1));
                    if (part > 255) {
                        return null;
                    }
                    bytes[i] = (byte) part;
                }
                return InetAddress.getByAddress(bytes);
            }
            if (IPV6.matcher(value).matches()) {
                // Brackets make the JDK parse an IPv6 literal and never ask DNS. A mapped IPv4
                // address such as ::ffff:203.0.113.7 comes back as an Inet4Address.
                return InetAddress.getByName("[" + value + "]");
            }
        } catch (UnknownHostException | NumberFormatException e) {
            return null;
        }
        return null;
    }

    private boolean takeSlot(KeycloakSessionFactory factory, String base, int slots) {
        for (int slot = 1; slot <= slots; slot++) {
            final String key = base + slot;
            try {
                Boolean taken = KeycloakModelUtils.runJobInTransactionWithResult(factory,
                      session -> session.singleUseObjects().putIfAbsent(key, windowSeconds));
                if (Boolean.TRUE.equals(taken)) {
                    return true;
                }
            } catch (RuntimeException e) {
                // A racing request took this slot first. Try the next one. The key holds no address.
                logger.debugf("Magic link slot %d not taken: %s", slot, e.getClass().getSimpleName());
            }
        }
        return false;
    }

    static String digest(String value) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                  .digest(value.trim().toLowerCase(Locale.ROOT).getBytes(StandardCharsets.UTF_8));
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

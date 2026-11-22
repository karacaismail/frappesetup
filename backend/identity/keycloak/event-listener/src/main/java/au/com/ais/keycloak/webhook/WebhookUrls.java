package au.com.ais.keycloak.webhook;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Checks the webhook URL (contract section 11): HTTPS, or plain HTTP to a host on a fixed list.
 * The body carries user ids. A signature protects integrity only, so plain HTTP would let anyone on the
 * network read it.
 *
 * <p>Added in this fork. Not part of the upstream project.
 */
final class WebhookUrls {

    private WebhookUrls() {
    }

    static URI check(String url, Set<String> plainHttpHosts) {
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
        if ("http".equals(target.getScheme()) && plainHttpHosts.contains(host.toLowerCase(Locale.ROOT))) {
            return target;
        }
        throw new IllegalArgumentException("webhook URL must use https; plain http only for a listed host");
    }

    /** Reads one host per line. A missing file means no host may use plain HTTP. */
    static Set<String> loadPlainHttpHosts(Path file) {
        if (!Files.isRegularFile(file)) {
            return Set.of();
        }
        try {
            return Files.readAllLines(file, StandardCharsets.UTF_8).stream()
                    .map(String::trim)
                    .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                    .map(line -> line.toLowerCase(Locale.ROOT))
                    .collect(Collectors.toUnmodifiableSet());
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}

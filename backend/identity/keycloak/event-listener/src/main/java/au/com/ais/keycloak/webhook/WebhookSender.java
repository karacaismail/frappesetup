package au.com.ais.keycloak.webhook;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;
import org.jboss.logging.Logger;

/**
 * Sends one signed request and retries a bounded number of times.
 *
 * <p>Every attempt is signed again with a new timestamp. The contract asks for this: the service
 * rejects a timestamp older than 300 seconds and a signature it has already accepted. Only a network
 * error, 429 and 5xx are retried. Other answers end the delivery. A lost event is found later by the
 * manual reconcile command of identity-sync. There is no background queue.
 *
 * <p>Added in this fork. The upstream project sent once and signed only the body.
 */
final class WebhookSender {

    private static final Logger LOG = Logger.getLogger(WebhookSender.class);

    private final HttpClient http;
    private final URI url;
    private final WebhookSigner signer;
    private final LongSupplier clockSeconds;
    private final int maxAttempts;
    private final Duration firstDelay;
    private final Duration requestTimeout;

    WebhookSender(HttpClient http, URI url, WebhookSigner signer, LongSupplier clockSeconds,
                  int maxAttempts, Duration firstDelay, Duration requestTimeout) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be at least 1");
        }
        this.http = http;
        this.url = url;
        this.signer = signer;
        this.clockSeconds = clockSeconds;
        this.maxAttempts = maxAttempts;
        this.firstDelay = firstDelay;
        this.requestTimeout = requestTimeout;
    }

    /** Completes with the last HTTP status, or -1 when no answer came. Never completes exceptionally. */
    CompletableFuture<Integer> send(byte[] body) {
        return attempt(body, 1);
    }

    private CompletableFuture<Integer> attempt(byte[] body, int number) {
        long timestamp = clockSeconds.getAsLong();
        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(requestTimeout)
                .header("Content-Type", "application/json")
                .header(WebhookSigner.TIMESTAMP_HEADER, Long.toString(timestamp))
                .header(WebhookSigner.SIGNATURE_HEADER, signer.sign(timestamp, WebhookSigner.MODE_EXECUTE, body))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        return http.sendAsync(request, HttpResponse.BodyHandlers.discarding())
                .handle((response, error) -> error == null ? response.statusCode() : -1)
                .thenCompose(status -> {
                    boolean retryable = status == -1 || status == 429 || status >= 500;
                    if (!retryable) {
                        if (status >= 300) LOG.warnf("Webhook rejected: HTTP %d", status);
                        else LOG.debugf("Webhook delivered: HTTP %d", status);
                        return CompletableFuture.completedFuture(status);
                    }
                    if (number >= maxAttempts) {
                        LOG.warnf("Webhook delivery failed after %d attempts (last status %d)", number, status);
                        return CompletableFuture.completedFuture(status);
                    }
                    long delay = firstDelay.toMillis() << (number - 1);
                    return CompletableFuture.supplyAsync(() -> null,
                                    CompletableFuture.delayedExecutor(delay, TimeUnit.MILLISECONDS))
                            .thenCompose(ignored -> attempt(body, number + 1));
                });
    }
}

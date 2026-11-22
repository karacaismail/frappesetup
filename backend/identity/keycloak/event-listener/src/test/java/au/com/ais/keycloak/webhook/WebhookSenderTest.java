package au.com.ais.keycloak.webhook;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/**
 * The contract says: a sender that sends the same event again signs it again with a new timestamp.
 * The service rejects a timestamp older than 300 seconds and a signature it has already seen.
 */
class WebhookSenderTest {

    private static final String SECRET = "test-secret-0123456789abcdef"; // gitleaks:allow (synthetic test value)
    private static final byte[] BODY = "{\"id\":\"e1\",\"realmId\":\"r1\"}".getBytes(StandardCharsets.UTF_8);

    record Received(String path, String timestamp, String signature, String contentType, String body) {}

    private HttpServer server;
    private final List<Received> received = new CopyOnWriteArrayList<>();

    private URI start(int... statuses) throws Exception {
        AtomicInteger call = new AtomicInteger();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            byte[] body = exchange.getRequestBody().readAllBytes();
            received.add(new Received(exchange.getRequestURI().toString(),
                    exchange.getRequestHeaders().getFirst(WebhookSigner.TIMESTAMP_HEADER),
                    exchange.getRequestHeaders().getFirst(WebhookSigner.SIGNATURE_HEADER),
                    exchange.getRequestHeaders().getFirst("Content-Type"),
                    new String(body, StandardCharsets.UTF_8)));
            int index = call.getAndIncrement();
            int status = index < statuses.length ? statuses[index] : 200;
            if (status == 307) {
                exchange.getResponseHeaders().add("Location", "/elsewhere");
            }
            exchange.sendResponseHeaders(status, -1);
            exchange.close();
        });
        server.start();
        return URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/v1/events");
    }

    @AfterEach
    void stop() {
        if (server != null) server.stop(0);
    }

    private static WebhookSender sender(URI url, AtomicLong clock, int maxAttempts) {
        return new WebhookSender(HttpClient.newHttpClient(), url, new WebhookSigner(SECRET),
                clock::getAndIncrement, maxAttempts, Duration.ofMillis(10), Duration.ofSeconds(5));
    }

    @Test
    void sendsSignedExecuteRequest() throws Exception {
        URI url = start(200);
        int status = sender(url, new AtomicLong(1795000000L), 3).send(BODY).get(10, TimeUnit.SECONDS);
        assertEquals(200, status);
        assertEquals(1, received.size());
        Received request = received.get(0);
        assertEquals("/v1/events", request.path());
        assertEquals("1795000000", request.timestamp());
        assertEquals("sha256=f2b645cac4297bc72e18f89026f6eec766e3ec08a374a15f7f0744cabf6c84ec", request.signature());
        assertEquals("application/json", request.contentType());
        assertEquals(new String(BODY, StandardCharsets.UTF_8), request.body());
    }

    @Test
    void retryIsSignedAgainWithANewTimestamp() throws Exception {
        URI url = start(503, 200);
        int status = sender(url, new AtomicLong(1795000000L), 3).send(BODY).get(10, TimeUnit.SECONDS);
        assertEquals(200, status);
        assertEquals(2, received.size());
        assertEquals("1795000000", received.get(0).timestamp());
        assertEquals("1795000001", received.get(1).timestamp());
        assertEquals("sha256=0c2e980567c37ed4dce4391b21665ae04c681daca6ce97062286570579c8a0e7",
                received.get(1).signature());
        assertNotEquals(received.get(0).signature(), received.get(1).signature());
    }

    @Test
    void clientErrorIsNotRetried() throws Exception {
        URI url = start(401, 200);
        int status = sender(url, new AtomicLong(1795000000L), 3).send(BODY).get(10, TimeUnit.SECONDS);
        assertEquals(401, status);
        assertEquals(1, received.size());
    }

    @Test
    void redirectIsNotFollowed() throws Exception {
        URI url = start(307, 200);
        HttpClient noRedirect = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).build();
        WebhookSender sender = new WebhookSender(noRedirect, url, new WebhookSigner(SECRET),
                new AtomicLong(1795000000L)::getAndIncrement, 3, Duration.ofMillis(10), Duration.ofSeconds(5));
        assertEquals(307, sender.send(BODY).get(10, TimeUnit.SECONDS));
        assertEquals(1, received.size());
        assertEquals("/v1/events", received.get(0).path());
    }

    @Test
    void factoryClientDoesNotFollowRedirects() {
        assertEquals(HttpClient.Redirect.NEVER, WebhookEventListenerProviderFactory.newHttpClient().followRedirects());
    }

    @Test
    void attemptsAreBounded() throws Exception {
        URI url = start(503, 503, 503, 200);
        int status = sender(url, new AtomicLong(1795000000L), 3).send(BODY).get(10, TimeUnit.SECONDS);
        assertEquals(503, status);
        assertEquals(3, received.size());
    }

    @Test
    void unreachableReceiverEndsWithoutThrowing() throws Exception {
        URI url = start();
        server.stop(0);
        server = null;
        int status = sender(url, new AtomicLong(1795000000L), 2).send(BODY).get(10, TimeUnit.SECONDS);
        assertEquals(-1, status);
    }
}

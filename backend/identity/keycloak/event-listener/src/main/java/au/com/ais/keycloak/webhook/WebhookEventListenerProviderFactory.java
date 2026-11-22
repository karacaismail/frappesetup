/*
 * Modified by this project from sashyo/keycloak-webhook-listener (Apache-2.0),
 * commit 5f23e5530db15c9042d8977c46a19758aa0ede97. Changes: the secret and the URL are checked at
 * start, the sender signs with a timestamp and retries a bounded number of times. See NOTICE.
 */
package au.com.ais.keycloak.webhook;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import org.jboss.logging.Logger;
import org.keycloak.Config;
import org.keycloak.events.EventListenerProvider;
import org.keycloak.events.EventListenerProviderFactory;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;

public class WebhookEventListenerProviderFactory implements EventListenerProviderFactory {

    private static final Logger LOG = Logger.getLogger(WebhookEventListenerProviderFactory.class);

    // the name you pick in Realm settings -> Events -> Event listeners
    public static final String ID = "webhook";

    private static final int MAX_ATTEMPTS = 3;
    private static final Duration FIRST_RETRY_DELAY = Duration.ofSeconds(1);
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(10);

    private WebhookSender sender;

    @Override
    public void init(Config.Scope config) {
        // read from KC_SPI_EVENTS_LISTENER__WEBHOOK__URL / __SECRET
        String url = config.get("url");
        String secret = config.get("secret");
        if (url == null || url.isBlank()) {
            LOG.warn("Webhook listener has no URL. Events are not sent.");
            return;
        }
        // A wrong URL, or a missing or short secret, stops Keycloak from starting. An unsigned request is never sent.
        URI target = WebhookUrls.check(url);
        WebhookSigner signer = new WebhookSigner(secret);
        sender = new WebhookSender(newHttpClient(), target, signer, () -> System.currentTimeMillis() / 1000L,
                MAX_ATTEMPTS, FIRST_RETRY_DELAY, REQUEST_TIMEOUT);
    }

    static HttpClient newHttpClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public EventListenerProvider create(KeycloakSession session) {
        return new WebhookEventListenerProvider(session, sender);
    }

    @Override
    public String getId() {
        return ID;
    }

    @Override
    public void postInit(KeycloakSessionFactory factory) {
    }

    @Override
    public void close() {
    }
}

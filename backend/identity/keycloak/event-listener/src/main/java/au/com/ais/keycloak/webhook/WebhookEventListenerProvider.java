/*
 * Modified by this project from sashyo/keycloak-webhook-listener (Apache-2.0),
 * commit 5f23e5530db15c9042d8977c46a19758aa0ede97. Changes: the body is Keycloak's own event format
 * with realmId and only the event types identity-sync processes; signing and delivery moved to
 * WebhookSigner and WebhookSender. See NOTICE.
 */
package au.com.ais.keycloak.webhook;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Map;
import java.util.Optional;
import org.keycloak.events.Event;
import org.keycloak.events.EventListenerProvider;
import org.keycloak.events.admin.AdminEvent;
import org.keycloak.models.AbstractKeycloakTransaction;
import org.keycloak.models.KeycloakSession;
import org.keycloak.util.JsonSerialization;

public class WebhookEventListenerProvider implements EventListenerProvider {

    private final KeycloakSession session;
    private final WebhookSender sender;

    public WebhookEventListenerProvider(KeycloakSession session, WebhookSender sender) {
        this.session = session;
        this.sender = sender;
    }

    @Override
    public void onEvent(Event event) {
        send(EventPayloads.user(event));
    }

    // The representation is never sent, so includeRepresentation is ignored.
    @Override
    public void onEvent(AdminEvent event, boolean includeRepresentation) {
        send(EventPayloads.admin(event));
    }

    private void send(Optional<Map<String, Object>> body) {
        if (sender == null || body.isEmpty()) return; // not configured or not forwarded: do nothing
        byte[] json = toJson(body.get());
        // only fire once Keycloak's transaction has committed - never for rolled-back changes
        session.getTransactionManager().enlistAfterCompletion(new AbstractKeycloakTransaction() {
            @Override
            protected void commitImpl() {
                // async: a slow webhook must never slow down a user's login
                sender.send(json);
            }

            @Override
            protected void rollbackImpl() {
            }
        });
    }

    private static byte[] toJson(Object value) {
        try {
            return JsonSerialization.writeValueAsBytes(value);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    @Override
    public void close() {
    }
}

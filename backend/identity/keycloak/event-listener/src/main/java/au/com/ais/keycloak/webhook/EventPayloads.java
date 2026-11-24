package au.com.ais.keycloak.webhook;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.keycloak.events.Event;
import org.keycloak.events.EventType;
import org.keycloak.events.admin.AdminEvent;
import org.keycloak.events.admin.OperationType;

/**
 * Builds the request body from a Keycloak event.
 *
 * <p>The body uses Keycloak's own field names and carries {@code realmId}, as the identity-sync
 * contract asks (KeycloakUserEvent, KeycloakAdminEvent). Only the event types the service processes
 * are sent. Fields the service does not read are left out: IP address, details, representation and
 * the acting admin. This keeps personal data out of the request.
 *
 * <p>Added in this fork. The upstream project sent every event with its own field names.
 */
final class EventPayloads {

    private static final Set<EventType> USER_TYPES =
            Set.of(EventType.REGISTER, EventType.VERIFY_EMAIL, EventType.UPDATE_EMAIL, EventType.DELETE_ACCOUNT);
    private static final Set<OperationType> USER_OPERATIONS =
            Set.of(OperationType.CREATE, OperationType.UPDATE, OperationType.DELETE);
    private static final Set<OperationType> MEMBERSHIP_OPERATIONS =
            Set.of(OperationType.CREATE, OperationType.DELETE);

    private EventPayloads() {
    }

    static Optional<Map<String, Object>> user(Event event) {
        if (event.getType() == null || !USER_TYPES.contains(event.getType())) {
            return Optional.empty();
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", event.getId());
        body.put("time", event.getTime());
        body.put("type", event.getType().name());
        body.put("realmId", event.getRealmId());
        body.put("clientId", event.getClientId());
        body.put("userId", event.getUserId());
        body.values().removeIf(value -> value == null);
        return Optional.of(body);
    }

    static Optional<Map<String, Object>> admin(AdminEvent event) {
        String resource = event.getResourceTypeAsString();
        OperationType operation = event.getOperationType();
        boolean forwarded = operation != null
                && (("USER".equals(resource) && USER_OPERATIONS.contains(operation))
                    || ("ORGANIZATION_MEMBERSHIP".equals(resource) && MEMBERSHIP_OPERATIONS.contains(operation)));
        if (!forwarded) {
            return Optional.empty();
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", event.getId());
        body.put("time", event.getTime());
        body.put("realmId", event.getRealmId());
        body.put("operationType", operation.name());
        body.put("resourceType", resource);
        body.put("resourcePath", event.getResourcePath());
        body.values().removeIf(value -> value == null);
        return Optional.of(body);
    }
}

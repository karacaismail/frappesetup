package au.com.ais.keycloak.webhook;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.keycloak.events.Event;
import org.keycloak.events.EventType;
import org.keycloak.events.admin.AdminEvent;
import org.keycloak.events.admin.OperationType;
import org.keycloak.events.admin.ResourceType;

/**
 * Expected fields come from the identity-sync contract (KeycloakUserEvent, KeycloakAdminEvent):
 * Keycloak's own field names with realmId. Personal data the service does not use is left out.
 */
class EventPayloadsTest {

    private static Event userEvent(EventType type) {
        Event event = new Event();
        event.setId("evt-1");
        event.setTime(1795000000900L);
        event.setType(type);
        event.setRealmId("realm-uuid");
        event.setRealmName("platform");
        event.setClientId("account");
        event.setUserId("user-uuid");
        event.setSessionId("session-uuid");
        event.setIpAddress("203.0.113.7");
        event.setDetails(Map.of("email", "ayse@example.test"));
        return event;
    }

    private static AdminEvent adminEvent(ResourceType resource, OperationType operation, String path) {
        AdminEvent event = new AdminEvent();
        event.setId("adm-1");
        event.setTime(1795000001000L);
        event.setRealmId("realm-uuid");
        event.setRealmName("platform");
        event.setResourceType(resource);
        event.setOperationType(operation);
        event.setResourcePath(path);
        event.setRepresentation("{\"email\":\"ayse@example.test\"}");
        return event;
    }

    @Test
    void userEventUsesKeycloakFieldsWithRealmId() {
        Map<String, Object> body = EventPayloads.user(userEvent(EventType.UPDATE_EMAIL)).orElseThrow();
        assertEquals(Map.of(
                "id", "evt-1",
                "time", 1795000000900L,
                "type", "UPDATE_EMAIL",
                "realmId", "realm-uuid",
                "clientId", "account",
                "userId", "user-uuid"), body);
    }

    @Test
    void userEventCarriesNoAddressDetailsOrRealmName() {
        Map<String, Object> body = EventPayloads.user(userEvent(EventType.REGISTER)).orElseThrow();
        assertTrue(!body.containsKey("ipAddress") && !body.containsKey("details") && !body.containsKey("realm"));
    }

    @Test
    void forwardsOnlyTheUserTypesTheServiceProcesses() {
        for (EventType type : new EventType[] {EventType.REGISTER, EventType.VERIFY_EMAIL,
                EventType.UPDATE_EMAIL, EventType.DELETE_ACCOUNT}) {
            assertTrue(EventPayloads.user(userEvent(type)).isPresent(), type.name());
        }
        for (EventType type : new EventType[] {EventType.LOGIN, EventType.LOGIN_ERROR, EventType.LOGOUT,
                EventType.CODE_TO_TOKEN, EventType.UPDATE_PASSWORD}) {
            assertEquals(Optional.empty(), EventPayloads.user(userEvent(type)), type.name());
        }
    }

    @Test
    void adminEventUsesKeycloakFieldsWithoutRepresentation() {
        Map<String, Object> body = EventPayloads.admin(
                adminEvent(ResourceType.USER, OperationType.UPDATE, "users/user-uuid")).orElseThrow();
        assertEquals(Map.of(
                "id", "adm-1",
                "time", 1795000001000L,
                "realmId", "realm-uuid",
                "operationType", "UPDATE",
                "resourceType", "USER",
                "resourcePath", "users/user-uuid"), body);
    }

    @Test
    void forwardsUserAndMembershipAdminEventsOnly() {
        assertTrue(EventPayloads.admin(adminEvent(ResourceType.USER, OperationType.CREATE, "users/u")).isPresent());
        assertTrue(EventPayloads.admin(adminEvent(ResourceType.USER, OperationType.DELETE, "users/u")).isPresent());
        assertTrue(EventPayloads.admin(adminEvent(ResourceType.ORGANIZATION_MEMBERSHIP, OperationType.CREATE,
                "organizations/o/members")).isPresent());
        assertTrue(EventPayloads.admin(adminEvent(ResourceType.ORGANIZATION_MEMBERSHIP, OperationType.DELETE,
                "organizations/o/members/u")).isPresent());
        assertEquals(Optional.empty(), EventPayloads.admin(
                adminEvent(ResourceType.CLIENT, OperationType.UPDATE, "clients/c")));
        assertEquals(Optional.empty(), EventPayloads.admin(
                adminEvent(ResourceType.REALM_ROLE, OperationType.CREATE, "roles/r")));
        assertEquals(Optional.empty(), EventPayloads.admin(
                adminEvent(ResourceType.USER, OperationType.ACTION, "users/u/reset-password")));
    }
}

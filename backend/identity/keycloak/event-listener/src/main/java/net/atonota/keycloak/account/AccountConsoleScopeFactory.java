package net.atonota.keycloak.account;

import java.util.Objects;

import org.keycloak.Config;
import org.keycloak.events.Event;
import org.keycloak.events.EventListenerProvider;
import org.keycloak.events.EventListenerProviderFactory;
import org.keycloak.events.admin.AdminEvent;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.RealmModel;

public final class AccountConsoleScopeFactory implements EventListenerProviderFactory, EventListenerProvider {
    @Override
    public String getId() {
        return "atonota-account-console-scope";
    }

    @Override
    public void postInit(KeycloakSessionFactory factory) {
        factory.register(event -> {
            if (event instanceof RealmModel.RealmPostCreateEvent created) {
                var realm = created.getCreatedRealm();
                if ("platform".equals(realm.getName()) && "atonota".equals(realm.getAccountTheme())) {
                    // Keycloak creates account-console before importing the realm's scopes.
                    // Attach roles once the scope exists, preserving the built-in client's role mappings.
                    var console = Objects.requireNonNull(realm.getClientByClientId("account-console"),
                        "Missing platform account-console client");
                    var roles = realm.getClientScopesStream()
                        .filter(scope -> "roles".equals(scope.getName()) && "openid-connect".equals(scope.getProtocol()))
                        .findFirst()
                        .orElseThrow(() -> new IllegalStateException("Missing platform OpenID Connect roles scope"));
                    console.addClientScope(roles, true);
                }
            }
        });
    }

    @Override
    public EventListenerProvider create(KeycloakSession session) {
        return this;
    }

    @Override
    public void init(Config.Scope config) {
    }

    @Override
    public void onEvent(Event event) {
    }

    @Override
    public void onEvent(AdminEvent event, boolean includeRepresentation) {
    }

    @Override
    public void close() {
    }
}

package net.atonota.keycloak.mcp;

import java.util.Collection;
import java.util.List;

import org.keycloak.Config;
import org.keycloak.OAuth2Constants;
import org.keycloak.common.util.Environment;
import org.keycloak.models.ClientModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.idm.ClientRepresentation;
import org.keycloak.representations.idm.ClientPolicyExecutorConfigurationRepresentation;
import org.keycloak.services.clientpolicy.ClientPolicyContext;
import org.keycloak.services.clientpolicy.ClientPolicyEvent;
import org.keycloak.services.clientpolicy.ClientPolicyException;
import org.keycloak.services.clientpolicy.context.AuthorizationRequestContext;
import org.keycloak.services.clientpolicy.context.ClientCRUDContext;
import org.keycloak.services.clientpolicy.context.PreAuthorizationRequestContext;
import org.keycloak.services.clientpolicy.context.TokenRequestContext;
import org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProvider;
import org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProviderFactory;

public final class McpRedirectPolicyFactory implements ClientPolicyExecutorProviderFactory {

    private static final String ID = "mcp-exact-redirect";
    private static final String MCP_CLIENT_MARKER = "mcp.external-client";

    @Override
    public ClientPolicyExecutorProvider<?> create(KeycloakSession session) {
        return new RedirectPolicy(session);
    }

    @Override
    public String getId() {
        return ID;
    }

    @Override
    public String getHelpText() {
        return "Requires one explicit redirect URI that exactly matches a secure registered MCP callback.";
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return List.of();
    }

    @Override
    public void init(Config.Scope config) {
    }

    @Override
    public void postInit(KeycloakSessionFactory factory) {
    }

    @Override
    public void close() {
    }

    private record RedirectPolicy(KeycloakSession session)
            implements ClientPolicyExecutorProvider<ClientPolicyExecutorConfigurationRepresentation> {

        @Override
        public String getProviderId() {
            return ID;
        }

        @Override
        public void executeOnEvent(ClientPolicyContext context) throws ClientPolicyException {
            switch (context) {
                case PreAuthorizationRequestContext authorization -> {
                    ClientModel client = session.getContext().getRealm().getClientByClientId(authorization.getClientId());
                    verify(client, authorization.getRequestParameters().get(OAuth2Constants.REDIRECT_URI));
                }
                case AuthorizationRequestContext authorization -> {
                    String redirect = authorization.getAuthorizationEndpointRequest().getRedirectUri();
                    verify(authorization.getClient(), redirect == null ? List.of() : List.of(redirect));
                }
                case TokenRequestContext token -> {
                    // TokenEndpoint strips control characters before constructing this policy context.
                    var form = session.getContext().getHttpRequest().getDecodedFormParameters();
                    verify(token.getClientSession().getClient(),
                            form == null ? null : form.get(OAuth2Constants.REDIRECT_URI));
                }
                case ClientCRUDContext registration -> verifyRegistration(registration);
                default -> {
                }
            }
        }

        private static void verify(ClientModel client, List<String> submitted) throws ClientPolicyException {
            if (client == null || !McpRedirect.matches(client.getRedirectUris(), submitted, Environment.isDevMode())) {
                throw new ClientPolicyException("invalid_request", "Invalid MCP redirect URI");
            }
        }

        private static void verifyRegistration(ClientCRUDContext registration) throws ClientPolicyException {
            if (registration.getEvent() != ClientPolicyEvent.REGISTER
                    && registration.getEvent() != ClientPolicyEvent.UPDATE) {
                return;
            }
            ClientRepresentation proposed = registration.getProposedClientRepresentation();
            ClientModel current = registration.getTargetClient();
            boolean proposedMcp = proposed != null && proposed.getAttributes() != null
                    && "true".equals(proposed.getAttributes().get(MCP_CLIENT_MARKER));
            boolean currentMcp = current != null && "true".equals(current.getAttribute(MCP_CLIENT_MARKER));
            if (!proposedMcp && !currentMcp) {
                return;
            }

            Collection<String> addresses = proposed == null ? null : proposed.getRedirectUris();
            if (addresses == null && current != null) {
                addresses = current.getRedirectUris();
            }
            if (!McpRedirect.allowsRegistration(addresses, Environment.isDevMode())) {
                throw new ClientPolicyException("invalid_request", "Invalid MCP redirect URI");
            }
        }
    }
}

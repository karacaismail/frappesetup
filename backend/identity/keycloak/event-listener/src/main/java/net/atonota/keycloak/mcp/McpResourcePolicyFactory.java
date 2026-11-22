package net.atonota.keycloak.mcp;

import java.util.List;

import org.keycloak.Config;
import org.keycloak.OAuth2Constants;
import org.keycloak.OAuthErrorException;
import org.keycloak.models.ClientModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.idm.ClientPolicyExecutorConfigurationRepresentation;
import org.keycloak.services.clientpolicy.ClientPolicyContext;
import org.keycloak.services.clientpolicy.ClientPolicyException;
import org.keycloak.services.clientpolicy.context.TokenRefreshContext;
import org.keycloak.services.clientpolicy.context.TokenRequestContext;
import org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProvider;
import org.keycloak.services.clientpolicy.executor.ClientPolicyExecutorProviderFactory;

/** Requires an explicit single resource before Keycloak issues an MCP access token. */
public final class McpResourcePolicyFactory implements ClientPolicyExecutorProviderFactory {
    static final String VERIFIED_RESOURCE = McpResourcePolicyFactory.class.getName() + ".verifiedResource";
    private static final String ID = "mcp-resource-required";
    private static final String EXPECTED_RESOURCE = "mcp.expected-resource";

    @Override
    public String getId() {
        return ID;
    }

    @Override
    public String getHelpText() {
        return "Require the configured MCP resource in every authorization-code and refresh token request.";
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return List.of();
    }

    @Override
    public ClientPolicyExecutorProvider<?> create(KeycloakSession session) {
        return new ResourcePolicy(session);
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

    private record ResourcePolicy(KeycloakSession session)
            implements ClientPolicyExecutorProvider<ClientPolicyExecutorConfigurationRepresentation> {
        @Override
        public String getProviderId() {
            return ID;
        }

        @Override
        public void executeOnEvent(ClientPolicyContext context) throws ClientPolicyException {
            if (context instanceof TokenRequestContext request) {
                verify(request.getClientSession().getClient());
            } else if (context instanceof TokenRefreshContext refresh) {
                verify(refresh.getClient());
            }
        }

        private void verify(ClientModel client) throws ClientPolicyException {
            var expected = client.getAttribute(EXPECTED_RESOURCE);
            // The grant context removes control characters. Compare the decoded request before that step.
            var form = session.getContext().getHttpRequest().getDecodedFormParameters();
            var supplied = form == null ? null : form.get(OAuth2Constants.RESOURCE);
            if (expected == null || expected.isBlank() || !List.of(expected).equals(supplied)) {
                throw new ClientPolicyException(OAuthErrorException.INVALID_TARGET, "An exact MCP resource is required.");
            }
            // KeycloakSession attributes live only for this request. Never reuse a grant's proof on refresh.
            session.setAttribute(VERIFIED_RESOURCE, expected);
        }
    }
}

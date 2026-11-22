package net.atonota.keycloak.mcp;

import java.util.List;

import org.keycloak.models.ClientSessionContext;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ProtocolMapperModel;
import org.keycloak.models.UserSessionModel;
import org.keycloak.protocol.oidc.mappers.AbstractOIDCProtocolMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAccessTokenMapper;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.IDToken;

/** Puts the verified token request resource into the signed access token. */
public final class McpExplicitResourceMapper extends AbstractOIDCProtocolMapper implements OIDCAccessTokenMapper {
    @Override
    public String getId() {
        return "mcp-explicit-resource";
    }

    @Override
    public String getDisplayType() {
        return "MCP explicit token request resource";
    }

    @Override
    public String getDisplayCategory() {
        return TOKEN_MAPPER_CATEGORY;
    }

    @Override
    public String getHelpText() {
        return "Adds the MCP resource only when the client policy verified the current token request.";
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return List.of();
    }

    @Override
    protected void setClaim(IDToken token, ProtocolMapperModel mapping, UserSessionModel userSession,
                            KeycloakSession session, ClientSessionContext clientSession) {
        var resource = session.getAttribute(McpResourcePolicyFactory.VERIFIED_RESOURCE, String.class);
        if (resource != null) {
            token.getOtherClaims().put("mcp_resource", resource);
        }
    }
}

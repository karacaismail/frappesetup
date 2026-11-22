package net.atonota.keycloak.headers;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerResponseContext;
import org.keycloak.headers.DefaultSecurityHeadersProvider;
import org.keycloak.headers.DefaultSecurityHeadersProviderFactory;
import org.keycloak.headers.SecurityHeadersProvider;
import org.keycloak.models.KeycloakSession;

public final class PlatformSecurityHeadersFactory extends DefaultSecurityHeadersProviderFactory {
    private static final String CSP = "Content-Security-Policy";
    private static final String OIDC_PATH = "realms/platform/protocol/openid-connect/";
    private static final Set<String> FRAME_PROBES = Set.of(
        OIDC_PATH + "3p-cookies/step1.html",
        OIDC_PATH + "3p-cookies/step2.html",
        OIDC_PATH + "login-status-iframe.html"
    );

    @Override
    public String getId() {
        return "platform-security-headers";
    }

    @Override
    public SecurityHeadersProvider create(KeycloakSession session) {
        return new DefaultSecurityHeadersProvider(session) {
            @Override
            public void addHeaders(ContainerRequestContext request, ContainerResponseContext response) {
                super.addHeaders(request, response);
                var headers = response.getHeaders();
                // Keycloak removes X-Frame-Options when an endpoint explicitly opts into framing.
                // Its CSP handling only removes the default 'self', leaving our 'none' on these probes.
                if ("GET".equals(request.getMethod()) && response.getStatus() == 200
                    && !headers.containsKey("X-Frame-Options") && headers.getFirst(CSP) instanceof String policy) {
                    String path = request.getUriInfo().getPath();
                    if (FRAME_PROBES.contains(path.startsWith("/") ? path.substring(1) : path)) {
                        headers.putSingle(CSP, Arrays.stream(policy.split(";"))
                            .map(String::trim)
                            .filter(directive -> !directive.isEmpty() && !directive.equals("frame-ancestors 'none'"))
                            .collect(Collectors.joining("; ")));
                    }
                }
            }
        };
    }
}

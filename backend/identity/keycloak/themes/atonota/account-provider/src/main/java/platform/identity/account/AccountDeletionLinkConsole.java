package platform.identity.account;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;

import org.keycloak.models.AccountRoles;
import org.keycloak.models.ClientModel;
import org.keycloak.models.Constants;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.RealmModel;
import org.keycloak.models.RoleModel;
import org.keycloak.models.UserModel;
import org.keycloak.services.managers.AppAuthManager;
import org.keycloak.services.managers.AuthenticationManager;
import org.keycloak.services.resources.account.AccountConsole;
import org.keycloak.theme.FreeMarkerException;
import org.keycloak.theme.Theme;
import org.keycloak.theme.freemarker.FreeMarkerProvider;

/**
 * Account console page with a link to the account deletion page of the product.
 *
 * <p>Rules (project record O-27, contract section 7):
 * <ul>
 *   <li>Keycloak's own "delete_account" action is not offered. It deletes the user in the first step.
 *       This class always switches the stock delete feature off in the page model.</li>
 *   <li>A customer gets a link to the deletion page instead. The address comes from the theme property
 *       {@value #URL_PROPERTY}, which the theme fills from a server setting.</li>
 *   <li>Only a customer gets the link. A customer holds the "delete-account" role of the "account"
 *       client. An invited employee does not hold it.</li>
 * </ul>
 *
 * <p>The decision is made here, on the server. A user without the role receives a page without the
 * link. Any missing piece (no session, no role, no address, unsafe address, missing text) means
 * "no link". The deletion page itself checks the user again. This link is not an access control.
 */
public class AccountDeletionLinkConsole extends AccountConsole {

    /** Page model key that the stock template writes into the page. */
    static final String STOCK_DELETE_FLAG = "deleteAccountAllowed";
    /** Theme property that holds the address of the deletion page. */
    static final String URL_PROPERTY = "accountDeletionUrl";
    /** Message keys of the two texts. */
    static final String INTRO_KEY = "atAccountDeletionIntro";
    static final String LINK_KEY = "atAccountDeletionLink";

    private static final String BODY_END = "</body>";

    private final Theme accountTheme;

    public AccountDeletionLinkConsole(KeycloakSession session, ClientModel client, Theme theme) {
        super(session, client, theme);
        this.accountTheme = theme;
    }

    @Override
    protected String renderAccountConsole(FreeMarkerProvider freeMarkerUtil, Map<String, Object> map)
            throws FreeMarkerException {
        map.put(STOCK_DELETE_FLAG, false);
        String page = super.renderAccountConsole(freeMarkerUtil, map);
        String section = deletionSection();
        int end = page.lastIndexOf(BODY_END);
        if (section == null || end < 0) {
            return page;
        }
        return page.substring(0, end) + section + page.substring(end);
    }

    /** Returns the markup of the link section, or null when the current user must not get it. */
    private String deletionSection() {
        RealmModel realm = session.getContext().getRealm();
        UserModel user = currentUser(realm);
        if (user == null || !isCustomer(realm, user)) {
            return null;
        }
        try {
            String address = safeAddress(accountTheme.getProperties().getProperty(URL_PROPERTY));
            if (address == null) {
                return null;
            }
            Locale locale = session.getContext().resolveLocale(user);
            Properties messages = accountTheme.getEnhancedMessages(realm, locale);
            String intro = messages.getProperty(INTRO_KEY);
            String link = messages.getProperty(LINK_KEY);
            if (isBlank(intro) || isBlank(link)) {
                return null;
            }
            return "<footer id=\"at-account-deletion\" class=\"at-account-deletion\">"
                    + "<p class=\"at-account-deletion__text\">" + escape(intro) + "</p>"
                    + "<a id=\"at-account-deletion-link\" href=\"" + escape(address) + "\""
                    + " class=\"at-account-deletion__link\">" + escape(link) + "</a>"
                    + "</footer>";
        } catch (IOException e) {
            return null;
        }
    }

    private UserModel currentUser(RealmModel realm) {
        AuthenticationManager.AuthResult authResult =
                new AppAuthManager().authenticateIdentityCookie(session, realm);
        return authResult == null ? null : authResult.user();
    }

    private static boolean isCustomer(RealmModel realm, UserModel user) {
        ClientModel accountClient = realm.getClientByClientId(Constants.ACCOUNT_MANAGEMENT_CLIENT_ID);
        if (accountClient == null) {
            return false;
        }
        RoleModel deleteRole = accountClient.getRole(AccountRoles.DELETE_ACCOUNT);
        return deleteRole != null && user.hasRole(deleteRole);
    }

    /**
     * Accepts only an absolute http or https address with a host. Returns null for anything else,
     * for example an empty value, a relative path or a "javascript:" address.
     */
    static String safeAddress(String value) {
        if (isBlank(value)) {
            return null;
        }
        try {
            URI uri = new URI(value.trim());
            String scheme = uri.getScheme();
            boolean web = "https".equalsIgnoreCase(scheme) || "http".equalsIgnoreCase(scheme);
            if (!web || isBlank(uri.getHost()) || uri.getUserInfo() != null) {
                return null;
            }
            return uri.toASCIIString();
        } catch (URISyntaxException e) {
            return null;
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    /** Escapes a value for use in HTML text and in a double-quoted attribute. */
    static String escape(String value) {
        StringBuilder out = new StringBuilder(value.length() + 16);
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '&' -> out.append("&amp;");
                case '<' -> out.append("&lt;");
                case '>' -> out.append("&gt;");
                case '"' -> out.append("&quot;");
                case '\'' -> out.append("&#39;");
                default -> out.append(c);
            }
        }
        return out.toString();
    }
}

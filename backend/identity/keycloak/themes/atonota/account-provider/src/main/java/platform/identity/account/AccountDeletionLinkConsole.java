package platform.identity.account;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;

import org.jboss.logging.Logger;
import org.keycloak.models.ClientModel;
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
 *   <li>Only a customer gets the link. A customer holds the realm role {@value #CUSTOMER_ROLE}.
 *       An invited employee does not hold it. The role is not Keycloak's "delete-account" role:
 *       that role authorises Keycloak's own delete action and must not be granted to anyone.</li>
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
    /** Realm role that marks a user who may ask for the deletion of the own account. */
    static final String CUSTOMER_ROLE = "request-account-deletion";
    /** Message keys of the two texts. */
    static final String INTRO_KEY = "atAccountDeletionIntro";
    static final String LINK_KEY = "atAccountDeletionLink";

    private static final String BODY_END = "</body>";
    private static final Logger LOG = Logger.getLogger(AccountDeletionLinkConsole.class);

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
        String section;
        try {
            section = deletionSection();
        } catch (RuntimeException e) {
            // The link is an addition. A failure here must not take the whole account console down.
            LOG.warn("Account deletion link was not added because of an unexpected error", e);
            return page;
        }
        if (section == null) {
            return page;
        }
        int end = page.lastIndexOf(BODY_END);
        if (end < 0) {
            LOG.warn("Account deletion link was not added: the account console page has no closing body tag");
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
            // From here on the user is a customer. A missing piece is a configuration mistake:
            // customers would lose their way to delete the account, so it is written to the log.
            String address = safeAddress(accountTheme.getProperties().getProperty(URL_PROPERTY));
            if (address == null) {
                LOG.warnf("Account deletion link is not shown: theme property '%s' is empty or not an absolute https address",
                        URL_PROPERTY);
                return null;
            }
            Locale locale = session.getContext().resolveLocale(user);
            Properties messages = accountTheme.getEnhancedMessages(realm, locale);
            String intro = messages.getProperty(INTRO_KEY);
            String link = messages.getProperty(LINK_KEY);
            if (isBlank(intro) || isBlank(link)) {
                LOG.warnf("Account deletion link is not shown: message '%s' or '%s' is missing for locale %s",
                        INTRO_KEY, LINK_KEY, locale);
                return null;
            }
            return "<footer id=\"at-account-deletion\" class=\"at-account-deletion\">"
                    + "<p class=\"at-account-deletion__text\">" + escape(intro) + "</p>"
                    + "<a id=\"at-account-deletion-link\" href=\"" + escape(address) + "\""
                    + " class=\"at-account-deletion__link\">" + escape(link) + "</a>"
                    + "</footer>";
        } catch (IOException e) {
            LOG.warn("Account deletion link is not shown: the account theme could not be read", e);
            return null;
        }
    }

    private UserModel currentUser(RealmModel realm) {
        AuthenticationManager.AuthResult authResult =
                new AppAuthManager().authenticateIdentityCookie(session, realm);
        return authResult == null ? null : authResult.user();
    }

    private static boolean isCustomer(RealmModel realm, UserModel user) {
        RoleModel customerRole = realm.getRole(CUSTOMER_ROLE);
        return customerRole != null && user.hasRole(customerRole);
    }

    /**
     * Accepts only an absolute https address with a host. Plain http is accepted for a local development
     * host only ("localhost" or a name that ends with ".localhost"). Returns null for anything else,
     * for example an empty value, a relative path or a "javascript:" address.
     */
    static String safeAddress(String value) {
        if (isBlank(value)) {
            return null;
        }
        try {
            URI uri = new URI(value.trim());
            String scheme = uri.getScheme();
            String host = uri.getHost();
            if (isBlank(host) || uri.getUserInfo() != null) {
                return null;
            }
            boolean secure = "https".equalsIgnoreCase(scheme);
            boolean localDevelopment = "http".equalsIgnoreCase(scheme) && isLocalHost(host);
            if (!secure && !localDevelopment) {
                return null;
            }
            return uri.toASCIIString();
        } catch (URISyntaxException e) {
            return null;
        }
    }

    private static boolean isLocalHost(String host) {
        String name = host.toLowerCase(Locale.ROOT);
        return name.equals("localhost") || name.endsWith(".localhost");
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

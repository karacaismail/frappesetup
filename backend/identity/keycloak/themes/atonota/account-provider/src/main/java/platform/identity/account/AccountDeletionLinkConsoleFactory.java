package platform.identity.account;

import org.keycloak.models.ClientModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.services.resources.account.AccountConsole;
import org.keycloak.services.resources.account.AccountConsoleFactory;
import org.keycloak.theme.Theme;

/**
 * Registers {@link AccountDeletionLinkConsole} under its own provider id.
 *
 * <p>An account theme selects it with the supported theme property
 * {@code accountResourceProvider=account-deletion-link}. Themes without that property keep the stock
 * console.
 */
public class AccountDeletionLinkConsoleFactory extends AccountConsoleFactory {

    public static final String PROVIDER_ID = "account-deletion-link";

    @Override
    public String getId() {
        return PROVIDER_ID;
    }

    @Override
    protected AccountConsole createAccountConsole(KeycloakSession session, ClientModel client, Theme theme) {
        return new AccountDeletionLinkConsole(session, client, theme);
    }
}

package platform.identity.account;

import java.util.Map;

import org.keycloak.authentication.requiredactions.DeleteAccount;
import org.keycloak.models.AccountRoles;
import org.keycloak.models.ClientModel;
import org.keycloak.models.Constants;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.RealmModel;
import org.keycloak.models.RequiredActionProviderModel;
import org.keycloak.models.RoleModel;
import org.keycloak.models.UserModel;
import org.keycloak.services.managers.AppAuthManager;
import org.keycloak.services.managers.AuthenticationManager;
import org.keycloak.services.resources.account.AccountConsole;
import org.keycloak.theme.FreeMarkerException;
import org.keycloak.theme.Theme;
import org.keycloak.theme.freemarker.FreeMarkerProvider;

/**
 * Account console page that offers account deletion only to a user who holds the
 * "delete-account" role of the "account" client.
 *
 * <p>The stock console also offers it to every user who holds "manage-account". Every user of the
 * console holds that role, so an invited employee would see the delete section too (project record
 * O-27). This class changes one value of the page model, on the server, before the page is rendered.
 * Nothing else of the stock console is changed. Keycloak still checks the role again when the
 * deletion itself is requested.
 */
public class DeleteRoleAccountConsole extends AccountConsole {

    /** Key of the page model value that the stock template writes into the page. */
    static final String DELETE_ACCOUNT_ALLOWED = "deleteAccountAllowed";

    public DeleteRoleAccountConsole(KeycloakSession session, ClientModel client, Theme theme) {
        super(session, client, theme);
    }

    @Override
    protected String renderAccountConsole(FreeMarkerProvider freeMarkerUtil, Map<String, Object> map)
            throws FreeMarkerException {
        map.put(DELETE_ACCOUNT_ALLOWED, isDeleteAccountAllowed());
        return super.renderAccountConsole(freeMarkerUtil, map);
    }

    /**
     * Returns true only when the signed-in user holds the "delete-account" role and the realm has
     * the delete action enabled. Any missing piece means "not allowed".
     */
    private boolean isDeleteAccountAllowed() {
        RealmModel realm = session.getContext().getRealm();
        AuthenticationManager.AuthResult authResult =
                new AppAuthManager().authenticateIdentityCookie(session, realm);
        if (authResult == null) {
            return false;
        }
        UserModel user = authResult.user();
        if (user == null) {
            return false;
        }
        RequiredActionProviderModel action = realm.getRequiredActionProviderByAlias(DeleteAccount.PROVIDER_ID);
        if (action == null || !action.isEnabled()) {
            return false;
        }
        ClientModel accountClient = realm.getClientByClientId(Constants.ACCOUNT_MANAGEMENT_CLIENT_ID);
        if (accountClient == null) {
            return false;
        }
        RoleModel deleteRole = accountClient.getRole(AccountRoles.DELETE_ACCOUNT);
        return deleteRole != null && user.hasRole(deleteRole);
    }
}

<#--
  ATONOTA: Source Keycloak 26.8.2, base/login/logout-confirm.ftl.
  Differences:
  1. The button has no positive tabindex. A positive tabindex breaks the natural Tab order (axe rule "tabindex").
  2. G-163: the screen asks which sessions to close. There are three separate choices.
     - This session: the form posts to Keycloak's logout action. This is the only scope that action knows.
     - Another session and every device: links to the device activity page of the account console.
       That page signs out one session or every session. Keycloak then sends a back-channel logout
       for each closed session, and Frappe and Press close their matching sessions.
     The login theme has no account console address. The link is built from the server path in front of
     "/resources/" and the realm name. The login address is no base: on this screen it may be a relative
     login-actions address.
     The page works without JavaScript and no choice is preselected.
-->
<#import "template.ftl" as layout>
<@layout.registrationLayout; section>
    <#if section = "header">
        ${msg("logoutConfirmTitle")}
    <#elseif section = "form">
        <#assign deviceActivityUrl = url.resourcesPath?keep_before("/resources/") + "/realms/" + realm.name?url('UTF-8') + "/account/account-security/device-activity">
        <div id="kc-logout-confirm" class="content-area">
            <p class="instruction">${msg("logoutScopeQuestion")}</p>

            <ul id="kc-logout-scopes" class="atonota-logout-scopes">
                <li class="atonota-logout-scope">
                    <h2 class="atonota-logout-scope-title">${msg("logoutScopeThisTitle")}</h2>
                    <p class="atonota-logout-scope-text">${msg("logoutScopeThisText")}</p>
                    <form class="form-actions" action="${url.logoutConfirmAction}" onsubmit="confirmLogout.disabled = true; return true;" method="POST">
                        <input type="hidden" name="session_code" value="${logoutConfirm.code}">
                        <div id="kc-form-buttons" class="${properties.kcFormGroupClass!}">
                            <input
                                   class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
                                   name="confirmLogout" id="kc-logout" type="submit" value="${msg("logoutThisSession")}"/>
                        </div>
                    </form>
                </li>
                <li class="atonota-logout-scope">
                    <h2 class="atonota-logout-scope-title">${msg("logoutScopeOtherTitle")}</h2>
                    <p class="atonota-logout-scope-text">${msg("logoutScopeOtherText")}</p>
                    <a id="kc-logout-other-session" href="${deviceActivityUrl}"
                       class="${properties.kcButtonSecondaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}">${msg("logoutOtherSession")}</a>
                </li>
                <li class="atonota-logout-scope">
                    <h2 class="atonota-logout-scope-title">${msg("logoutScopeAllTitle")}</h2>
                    <p class="atonota-logout-scope-text">${msg("logoutScopeAllText")}</p>
                    <a id="kc-logout-all-devices" href="${deviceActivityUrl}"
                       class="${properties.kcButtonSecondaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}">${msg("logoutAllDevices")}</a>
                </li>
            </ul>

            <div id="kc-info-message">
                <#if logoutConfirm.skipLink>
                <#else>
                    <#if (client.baseUrl)?has_content>
                        <p><a href="${client.baseUrl}">${msg("backToApplication")}</a></p>
                    </#if>
                </#if>
            </div>

            <div class="clearfix"></div>
        </div>
    </#if>
</@layout.registrationLayout>

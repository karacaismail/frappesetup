<#--
  ATONOTA: Source Keycloak 26.8.2, keycloak.v2/login/login.ftl.
  Differences:
  1. When Keycloak shows the e-mail only as text, the form holds a hidden username field.
     The macro is in account-field.ftl. Reason: AJA-648.
  2. The layout follows the approved draft (AJA-880, version 3, AJA-1125):
     a short intro under the title, and the forgot-password link after the sign-in button.
  3. An empty field is named under the field, not reported as a wrong password (AJA-1125).
     js/atonota-form.js checks both fields before sending. Without JavaScript the server
     still names an empty e-mail field. The texts come from the data-at-empty-* attributes.
-->
<#import "template.ftl" as layout>
<#import "field.ftl" as field>
<#import "buttons.ftl" as buttons>
<#import "social-providers.ftl" as identityProviders>
<#import "passkeys.ftl" as passkeys>
<#import "account-field.ftl" as account>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>
<!-- template: login.ftl -->

    <#if section = "header">
        ${msg("loginAccountTitle")}
    <#elseif section = "form">
        <#if !realm.loginWithEmailAllowed>
            <#assign atEmptyUsername = msg("atEmptyUsername")>
            <#assign atIntro = msg("atLoginIntroUsername")>
        <#elseif !realm.registrationEmailAsUsername>
            <#assign atEmptyUsername = msg("atEmptyUsernameOrEmail")>
            <#assign atIntro = msg("atLoginIntroUsernameOrEmail")>
        <#else>
            <#assign atEmptyUsername = msg("atEmptyEmail")>
            <#assign atIntro = msg("atLoginIntroEmail")>
        </#if>
        <#-- Keycloak reports an empty username like a wrong password. The theme names the empty field instead. -->
        <#assign atLoginError = messagesPerField.getFirstError('username','password')>
        <#if atLoginError?has_content && !(login.username!'')?has_content && !usernameHidden??>
            <#assign atLoginError = atEmptyUsername>
        </#if>
        <#if !usernameHidden??>
        <p class="at-intro">${atIntro}</p>
        </#if>
        <div id="kc-form">
          <div id="kc-form-wrapper">
            <#if realm.password>
                <form id="kc-form-login" class="${properties.kcFormClass!}" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post" novalidate="novalidate"
                      data-at-required="username password" data-at-empty-username="${atEmptyUsername}" data-at-empty-password="${msg("atEmptyPassword")}">
                    <#if !usernameHidden??>
                        <#assign label>
                            <#if !realm.loginWithEmailAllowed>${msg("username")}<#elseif !realm.registrationEmailAsUsername>${msg("usernameOrEmail")}<#else>${msg("email")}</#if>
                        </#assign>
                        <@field.input name="username" label=label error=atLoginError
                            autofocus=true autocomplete="${(enableWebAuthnConditionalUI?has_content)?then('username webauthn', 'username')}" value=login.username!'' />
                        <@field.password name="password" label=msg("password") error="" forgotPassword=false autofocus=usernameHidden?? autocomplete="current-password">
                            <#if realm.rememberMe && !usernameHidden??>
                                <@field.checkbox name="rememberMe" label=msg("rememberMe") value=login.rememberMe?? />
                            </#if>
                        </@field.password>
                    <#else>
                        <@account.usernameField/>
                        <@field.password name="password" label=msg("password") forgotPassword=false autofocus=usernameHidden?? autocomplete="current-password">
                            <#if realm.rememberMe && !usernameHidden??>
                                <@field.checkbox name="rememberMe" label=msg("rememberMe") value=login.rememberMe?? />
                            </#if>
                        </@field.password>
                    </#if>

                    <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>
                    <@buttons.loginButton />
                    <#-- ATONOTA 2: the draft puts this link after the sign-in button. -->
                    <#if realm.resetPasswordAllowed>
                    <p class="at-forgot">
                        <a id="at-forgot-password" href="${url.loginResetCredentialsUrl}" data-at-standalone>${msg("doForgotPassword")}</a>
                    </p>
                    </#if>
                </form>
            </#if>
            </div>
        </div>
        <@passkeys.conditionalUIData />
    <#elseif section = "socialProviders" >
        <#if realm.password && social.providers?? && social.providers?has_content>
            <@identityProviders.show social=social/>
        </#if>
    <#elseif section = "info" >
        <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
            <div id="kc-registration-container">
                <div id="kc-registration">
                    <span>${msg("noAccount")} <a href="${url.registrationUrl}">${msg("doRegister")}</a></span>
                </div>
            </div>
        </#if>
    </#if>

</@layout.registrationLayout>

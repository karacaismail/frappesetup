<#--
  ATONOTA: Source Keycloak 26.8.2, keycloak.v2/login/login-password.ftl.
  One difference: the form holds a hidden username field.
  The macro is in account-field.ftl. Reason: AJA-648.
-->
<#import "template.ftl" as layout>
<#import "field.ftl" as field>
<#import "buttons.ftl" as buttons>
<#import "passkeys.ftl" as passkeys>
<#import "account-field.ftl" as account>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('password'); section>
<!-- template: login-password.ftl -->
    <#if section = "header">
        ${msg("doLogIn")}
    <#elseif section = "form">
        <div id="kc-form">
            <div id="kc-form-wrapper">
                <form id="kc-form-login" class="${properties.kcFormClass!}" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post">
                    <@account.usernameField/>
                    <@field.password name="password" label=msg("password") forgotPassword=realm.resetPasswordAllowed autofocus=true autocomplete="current-password" />
                    <@buttons.loginButton />
                </form>
            </div>
        </div>
        <@passkeys.conditionalUIData />
    </#if>

</@layout.registrationLayout>

<#--
  ATONOTA: Source Keycloak 26.8.2, keycloak.v2/login/login-verify-email.ftl.
  Difference: the resend link is a full action sentence ("emailVerifyResend").
  The base template builds the sentence from three pieces. In Turkish the joined sentence reads badly.
-->
<#import "template.ftl" as layout>
<#import "buttons.ftl" as buttons>
<@layout.registrationLayout displayInfo=!isAppInitiatedAction??; section>
<!-- template: login-verify-email.ftl -->
    <#if section = "header">
        ${msg("emailVerifyTitle")}
    <#elseif section = "form">
        <p class="instruction">
            <#if verifyEmail??>
                ${msg("emailVerifyInstruction1",verifyEmail)}
            <#else>
                ${msg("emailVerifyInstruction4",user.email)}
            </#if>
        </p>
        <#if isAppInitiatedAction??>
            <form id="kc-verify-email-form" class="${properties.kcFormClass!}" action="${url.loginAction}" method="post">
                <@buttons.actionGroup horizontal=true>
                    <#if verifyEmail??>
                        <@buttons.button id="kc-resend" label="emailVerifyResend" type="secondary"/>
                    <#else>
                        <@buttons.button id="kc-send" label="emailVerifySend"/>
                    </#if>
                    <@buttons.button id="kc-cancel" label="doCancel" type="secondary" name="cancel-aia" value="true"/>
                </@buttons.actionGroup>
            </form>
        </#if>
    <#elseif section = "info">
        <#if !isAppInitiatedAction??>
            <p class="instruction at-link-line">
                <span>${msg("emailVerifyInstruction2")}</span>
                <a id="at-resend" href="${url.loginAction}">${msg("emailVerifyResend")}</a>
            </p>
        </#if>
    </#if>
</@layout.registrationLayout>

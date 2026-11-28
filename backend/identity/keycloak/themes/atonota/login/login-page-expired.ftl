<#--
  ATONOTA: Source Keycloak 26.8.2, base/login/login-page-expired.ftl.
  Difference: each of the two links is a full action sentence.
  The base template builds the sentence from pieces. In Turkish the joined sentence reads badly.
-->
<#import "template.ftl" as layout>
<@layout.registrationLayout; section>
    <#if section = "header">
        ${msg("pageExpiredTitle")}
    <#elseif section = "form">
        <p id="instruction1" class="instruction">${msg("atPageExpiredIntro")}</p>
        <ul class="at-link-list" role="list">
            <li><a id="loginRestartLink" href="${url.loginRestartFlowUrl}">${msg("atPageExpiredRestart")}</a></li>
            <li><a id="loginContinueLink" href="${url.loginAction}">${msg("atPageExpiredContinue")}</a></li>
        </ul>
    </#if>
</@layout.registrationLayout>

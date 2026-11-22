<#--
  ATONOTA: Kaynak Keycloak 26.8.2, base/login/login-page-expired.ftl.
  Fark: iki bağlantı tam birer eylem cümlesidir.
  Temel şablon cümleyi parçalardan birleştirir. Türkçede bu birleşim bozuk okunur.
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

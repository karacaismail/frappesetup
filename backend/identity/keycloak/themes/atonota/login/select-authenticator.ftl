<#--
  ATONOTA: Kaynak Keycloak 26.8.2, keycloak.v2/login/select-authenticator.ftl.
  Fark: her seçenek formun içinde gerçek bir gönder düğmesidir.
  Temel şablonda seçenek tıklanan bir "div" öğesidir. O öğe Enter ve Space tuşuyla çalışmaz.
  Her form ayrı kimlik taşır. Temel şablonda bütün formlar aynı kimliği taşır.
-->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayInfo=false; section>
<!-- template: select-authenticator.ftl -->

    <#if section = "header" || section = "show-username">
        <#if section = "header">
            ${msg("loginChooseAuthenticator")}
        </#if>
    <#elseif section = "form">

    <ul class="at-choice-list" role="list">
        <#list auth.authenticationSelections as authenticationSelection>
            <li>
                <form id="kc-select-credential-form-${authenticationSelection?index}" action="${url.loginAction}" method="post">
                    <input type="hidden" name="authenticationExecution" value="${authenticationSelection.authExecId}">
                    <button type="submit" class="at-choice" id="at-choice-${authenticationSelection?index}">
                        <span class="at-choice__icon" aria-hidden="true">
                            <i class="${properties['${authenticationSelection.iconCssClass}']!authenticationSelection.iconCssClass}"></i>
                        </span>
                        <span class="at-choice__text">
                            <span class="at-choice__title">${msg('${authenticationSelection.displayName}')}</span>
                            <span class="at-choice__help">${msg('${authenticationSelection.helpText}')}</span>
                        </span>
                        <span class="at-choice__arrow" aria-hidden="true">
                            <i class="${properties.kcSelectAuthListItemArrowIconClass!}"></i>
                        </span>
                    </button>
                </form>
            </li>
        </#list>
    </ul>

    </#if>
</@layout.registrationLayout>

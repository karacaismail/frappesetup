<#--
  ATONOTA: Source Keycloak 26.8.2, keycloak.v2/login/select-authenticator.ftl.
  Difference: each option is a real submit button inside a form.
  In the base template an option is a clickable "div" element. That element does not work with Enter or Space.
  Each form has its own id. In the base template all forms share the same id.
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

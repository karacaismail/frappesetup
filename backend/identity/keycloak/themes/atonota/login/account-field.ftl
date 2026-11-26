<#--
  ATONOTA: Theme macro, not a Keycloak copy (AJA-648).
  A password manager links a saved password to an account only through a field with
  autocomplete="username" in the same form. Keycloak shows the e-mail only as text on some password
  screens, so Chrome and Apple Passwords did not offer to save a changed password, or picked the wrong account.

  The field is hidden. It has no "name", so the server never receives it.
  type="text" is required: password managers ignore type="hidden".
  tabindex="-1" and aria-hidden keep it away from keyboard and screen reader users.
-->
<#macro usernameField>
  <#-- Keycloak gives "username" to required-action screens and "auth.attemptedUsername" to sign-in screens. -->
  <#assign atAccountUsername = (username?? && username?is_string)?then(username, '')>
  <#if !atAccountUsername?has_content>
    <#assign atAccountUsername = (auth.attemptedUsername)!''>
  </#if>
  <#if atAccountUsername?has_content>
    <div class="at-account-username" hidden aria-hidden="true">
      <input type="text" id="at-account-username" value="${atAccountUsername}" autocomplete="username" tabindex="-1">
    </div>
  </#if>
</#macro>

<#import "template.ftl" as layout>
<@layout.actionEmail
  title=msg("atActionsTitle")
  link=link
  label=msg("atActionsButton")
  expiry=msg("atExpiry", linkExpirationFormatter(linkExpiration))
  note=msg("atActionsNote")>
<@layout.paragraph>${msg("atActionsIntro", realmName)}</@layout.paragraph>
<#if requiredActions?? && requiredActions?size gt 0>
<ul style="margin:0 0 16px 0;padding:0 0 0 22px;${layout.textBody}">
<#list requiredActions as item>
<li style="margin:0 0 4px 0;${layout.textBody}">${msg("requiredAction.${item}")}</li>
</#list>
</ul>
</#if>
<@layout.paragraph>${msg("atActionsStart")}</@layout.paragraph>
</@layout.actionEmail>

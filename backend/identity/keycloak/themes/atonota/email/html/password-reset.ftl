<#import "template.ftl" as layout>
<@layout.actionEmail
  title=msg("atResetTitle")
  link=link
  label=msg("atResetButton")
  expiry=msg("atExpiry", linkExpirationFormatter(linkExpiration))
  note=msg("atResetNote")>
<@layout.paragraph>${msg("atResetIntro", realmName)}</@layout.paragraph>
</@layout.actionEmail>

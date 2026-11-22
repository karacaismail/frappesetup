<#import "template.ftl" as layout>
<@layout.actionEmail
  title=msg("atVerifyTitle")
  link=link
  label=msg("atVerifyButton")
  expiry=msg("atExpiry", linkExpirationFormatter(linkExpiration))
  note=msg("atVerifyNote")>
<@layout.paragraph>${msg("atVerifyIntro", realmName)}</@layout.paragraph>
</@layout.actionEmail>

<#--
  Cloudflight magic link email. The provider supplies the sign-in URL as "link".
-->
<#import "template.ftl" as layout>
<@layout.actionEmail
  title=msg("atMagicTitle")
  link=link
  label=msg("atMagicButton")
  expiry=msg("atMagicExpiry")
  note=msg("atMagicNote")>
<@layout.paragraph>${msg("atMagicIntro", realmName)}</@layout.paragraph>
<@layout.paragraph>${msg("atMagicBrowser")}</@layout.paragraph>
</@layout.actionEmail>

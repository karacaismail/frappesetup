<#--
  Sihirli bağlantı e-postası. Şablonu sky-cloak/keycloak-magic-link eklentisi çağırır.
  Eklenti yalnız "link" ve "clientName" değişkenlerini verir. Süre değişkeni vermez.
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

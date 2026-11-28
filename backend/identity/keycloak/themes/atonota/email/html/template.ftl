<#--
  Atonota e-mail layout. Every HTML e-mail uses the macros in this file.
  E-mail clients do not load external styles or scripts, so the styles are inline.
  There are no external scripts, styles, fonts or images.
  The visual values sit in one place below. They match the login theme's tokens.
-->
<#assign
  pageBg = "#f4f5f7"
  cardBg = "#ffffff"
  ink = "#1b1f24"
  quiet = "#4b5563"
  buttonBg = "#00aacc"
  buttonInk = "#1b1f24"
  linkInk = "#006f86"
  brandDot = "#00aacc"
  fontStack = "Outfit, 'Segoe UI', Helvetica, Arial, sans-serif"
  cardRadius = "16px"
  buttonRadius = "10px"
  textBody = "font-family:${fontStack};font-size:16px;line-height:24px;color:${ink};"
  textQuiet = "font-family:${fontStack};font-size:14px;line-height:22px;color:${quiet};"
>

<#-- Page frame: brand at the top, card in the middle, security note at the bottom. -->
<#macro frame title="" note="">
<!DOCTYPE html>
<html lang="${locale.language}" dir="${(ltr)?then('ltr','rtl')}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>${title?has_content?then(title, realmName)}</title>
</head>
<body style="margin:0;padding:0;background-color:${pageBg};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:${pageBg};">
<tr>
<td align="center" style="padding:24px 12px 32px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;">
<tr>
<td style="padding:0 8px 16px 8px;font-family:${fontStack};font-size:18px;line-height:24px;font-weight:600;color:${ink};">
<span style="display:inline-block;width:8px;height:8px;border:4px solid ${cardBg};border-radius:50%;background-color:${brandDot};vertical-align:middle;box-shadow:0 0 0 3px ${ink};"></span><span style="vertical-align:middle;">&nbsp;&nbsp;${realmName}</span>
</td>
</tr>
<tr>
<td style="padding:28px 20px 28px 20px;background-color:${cardBg};border-radius:${cardRadius};${textBody}">
<#nested>
</td>
</tr>
<tr>
<td style="padding:16px 8px 0 8px;${textQuiet}">
<#if note?has_content>
<p style="margin:0 0 8px 0;${textQuiet}">${note}</p>
</#if>
<p style="margin:0;${textQuiet}">${msg("atSentBy", realmName)}</p>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>
</#macro>

<#-- Keycloak's other built-in e-mails call this macro. Its name and signature do not change. -->
<#macro emailLayout>
<@frame>
<#nested>
</@frame>
</#macro>

<#macro heading text>
<h1 style="margin:0 0 12px 0;font-family:${fontStack};font-size:24px;line-height:30px;font-weight:600;color:${ink};">${text}</h1>
</#macro>

<#macro paragraph>
<p style="margin:0 0 16px 0;${textBody}"><#nested></p>
</#macro>

<#-- Main button with the plain link below it. If the button does not work, the user copies the address. -->
<#macro action link label expiry note="">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 20px 0;">
<tr>
<td align="center" style="background-color:${buttonBg};border-radius:${buttonRadius};">
<a href="${link}" style="display:block;padding:14px 16px;font-family:${fontStack};font-size:16px;line-height:24px;font-weight:600;color:${buttonInk};text-decoration:none;border-radius:${buttonRadius};">${label}</a>
</td>
</tr>
</table>
<p style="margin:0 0 8px 0;${textBody}">${expiry}</p>
<#-- The security note sits just below the button. The long address comes last, in the quiet colour. -->
<#if note?has_content>
<p style="margin:0 0 24px 0;${textBody}">${note}</p>
</#if>
<p style="margin:0 0 4px 0;${textQuiet}">${msg("atCopyHint")}</p>
<#-- Explicit exception: this line holds only the address. An address is not a word and cannot fit 320 pixels in a table cell any other way. -->
<p style="margin:0;${textQuiet}word-break:break-all;"><a href="${link}" style="color:${quiet};text-decoration:none;">${link}</a></p>
</#macro>

<#-- Action e-mail: heading, description (nested content), button, expiry and security note. -->
<#macro actionEmail title link label expiry note>
<@frame title=title>
<@heading text=title />
<#nested>
<@action link=link label=label expiry=expiry note=note />
</@frame>
</#macro>

<#ftl output_format="plainText">
${realmName}

${msg("atActionsTitle")}

${msg("atActionsIntro", realmName)}

<#if requiredActions??><#list requiredActions as item>- ${msg("requiredAction.${item}")}
</#list></#if>

${msg("atActionsStart")}

${link}

${msg("atExpiry", linkExpirationFormatter(linkExpiration))}

${msg("atActionsNote")}

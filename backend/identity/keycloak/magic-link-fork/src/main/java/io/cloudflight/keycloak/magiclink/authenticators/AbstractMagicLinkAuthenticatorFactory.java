/*
 * MODIFIED FILE. Changed by Atonota for G-162 on 24 November 2026.
 * Original: cloudflightio/keycloak-magic-link, commit 7b4ee949a39a7ee953987162479ae1da2c57c3cb,
 * keycloak-magic-link/src/main/java/io/cloudflight/keycloak/magiclink/authenticators/AbstractMagicLinkAuthenticatorFactory.java
 * Licensed under the Apache License, Version 2.0. The change notice is in magic-link-fork/NOTICE.
 * The upstream @author tag kept its name. Its e-mail address was left out: this repository holds
 * no personal e-mail addresses (backend/dev/tests/test_release_residue.py).
 *
 * Changes:
 * - getConfigProperties() also declares the send limit and the window (MagicLinkSendLimiter).
 *   Keycloak masks undeclared settings in the admin API, so they must be declared to be readable.
 */
package io.cloudflight.keycloak.magiclink.authenticators;

import static io.cloudflight.keycloak.magiclink.authenticators.MagicLinkValidityConstants.DEFAULT_VALIDITY_IN_SECONDS;
import static io.cloudflight.keycloak.magiclink.authenticators.MagicLinkValidityConstants.VALIDITY_DURATION_CONFIG_KEY;

import java.util.List;

import org.keycloak.Config;
import org.keycloak.authentication.AuthenticatorFactory;
import org.keycloak.models.AuthenticationExecutionModel;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.provider.ProviderConfigProperty;

import io.cloudflight.keycloak.magiclink.sending.MagicLinkSendLimiter;

/**
 * Common implementation for magic link authenticator factories.
 *
 * @author Ludwig Burtscher (Cloudflight)
 */
public abstract class AbstractMagicLinkAuthenticatorFactory implements AuthenticatorFactory {

    @Override
    public String getReferenceCategory() {
        return "otp";
    }

    @Override
    public boolean isConfigurable() {
        return true;
    }

    @Override
    public AuthenticationExecutionModel.Requirement[] getRequirementChoices() {
        return REQUIREMENT_CHOICES;
    }

    @Override
    public boolean isUserSetupAllowed() {
        return false;
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        ProviderConfigProperty magicKeyValidityDuration = new ProviderConfigProperty();
        magicKeyValidityDuration.setName(VALIDITY_DURATION_CONFIG_KEY);
        magicKeyValidityDuration.setLabel("MagicKey Validity Duration in seconds");
        magicKeyValidityDuration.setType(ProviderConfigProperty.INTEGER_TYPE);
        magicKeyValidityDuration.setHelpText("Duration in seconds that a magic key is valid");
        magicKeyValidityDuration.setRequired(true);
        magicKeyValidityDuration.setDefaultValue(DEFAULT_VALIDITY_IN_SECONDS);
        ProviderConfigProperty sendLimit = new ProviderConfigProperty();
        sendLimit.setName(MagicLinkSendLimiter.LIMIT_CONFIG_KEY);
        sendLimit.setLabel("Mails per address in the window");
        sendLimit.setType(ProviderConfigProperty.INTEGER_TYPE);
        sendLimit.setHelpText("How many magic link mails one address may receive in the window");
        sendLimit.setDefaultValue(MagicLinkSendLimiter.DEFAULT_LIMIT);
        ProviderConfigProperty sendWindow = new ProviderConfigProperty();
        sendWindow.setName(MagicLinkSendLimiter.WINDOW_CONFIG_KEY);
        sendWindow.setLabel("Send limit window in seconds");
        sendWindow.setType(ProviderConfigProperty.INTEGER_TYPE);
        sendWindow.setHelpText("Length of the sliding window for the send limit, in seconds");
        sendWindow.setDefaultValue(MagicLinkSendLimiter.DEFAULT_WINDOW_SECONDS);
        return List.of(magicKeyValidityDuration, sendLimit, sendWindow);
    }

    @Override
    public void init(Config.Scope scope) {
        // not needed
    }

    @Override
    public void postInit(KeycloakSessionFactory keycloakSessionFactory) {
        // not needed
    }

    @Override
    public void close() {
        // not needed
    }

}

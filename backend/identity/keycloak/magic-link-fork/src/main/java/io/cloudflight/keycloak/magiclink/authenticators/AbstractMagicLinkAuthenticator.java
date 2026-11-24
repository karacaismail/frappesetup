/*
 * MODIFIED FILE. Changed by Atonota for G-162 on 24 November 2026.
 * Original: cloudflightio/keycloak-magic-link, commit 7b4ee949a39a7ee953987162479ae1da2c57c3cb,
 * keycloak-magic-link/src/main/java/io/cloudflight/keycloak/magiclink/authenticators/AbstractMagicLinkAuthenticator.java
 * Licensed under the Apache License, Version 2.0. The change notice is in magic-link-fork/NOTICE.
 *
 * Changes:
 * - action() does the same work for an existing and an unknown address: it always makes a key, a link
 *   and a session id, writes the session id to the login session and queues one background job.
 *   The answer time no longer shows whether the account exists.
 * - The MAGIC_LINK_SESSION row and the mail are written in the background job, after the request.
 *   The row is written before the mail, so a link never arrives before its row.
 * - The job sends only within the per-address send limit (MagicLinkSendLimiter).
 * - A failed mail is logged without the link or the key. The answer is not a 500 error any more.
 */
package io.cloudflight.keycloak.magiclink.authenticators;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;

import org.jboss.logging.Logger;
import org.keycloak.authentication.AuthenticationFlowContext;
import org.keycloak.authentication.AuthenticationFlowError;
import org.keycloak.common.util.ObjectUtil;
import org.keycloak.common.util.Time;
import org.keycloak.connections.jpa.JpaConnectionProvider;
import org.keycloak.executors.ExecutorsProvider;
import org.keycloak.models.AuthenticatorConfigModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.models.KeycloakTransaction;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;
import org.keycloak.models.utils.KeycloakModelUtils;

import io.cloudflight.keycloak.magiclink.entity.MagicLinkSession;
import io.cloudflight.keycloak.magiclink.sending.EmailLinkSender;
import io.cloudflight.keycloak.magiclink.sending.LinkSender;
import io.cloudflight.keycloak.magiclink.sending.MagicLinkSendLimiter;
import jakarta.persistence.EntityManager;
import jakarta.ws.rs.core.Response;

/**
 * Common implementation for magic link authenticators.
 *
 * @author Ludwig Burtscher (ludwig.burtscher@cloudflight.io)
 */
public abstract class AbstractMagicLinkAuthenticator implements MagicLinkAuthenticator {

    protected static final String EMAIL_INPUT_FORM_TEMPLATE = "email-login.ftl";
    protected static final String EMAIL_ATTRIBUTE_FORM_NAME = "username";

    protected static final String MAGICKEY_QUERY_PARAM = "magickey";
    protected static final String MAGICLINK_SESSION_ID_KEY = "magiclink-session-id";

    /** Executor pool for the background mail jobs (G-162). */
    protected static final String SEND_EXECUTOR = "atonota-magic-link";

    private final LinkSender linkSender = new EmailLinkSender();
    private static final Logger logger = Logger.getLogger(AbstractMagicLinkAuthenticator.class);


    @Override
    public void action(AuthenticationFlowContext context) {
        // Get email from the submitted form
        final String email = getEmailAddressInput(context);
        if (ObjectUtil.isBlank(email)) {
            return;
        }

        // G-162: the same steps run for an existing and an unknown address.
        UserModel user = findUserByEmailAddress(context, email);
        final String magicKey = generateMagicKey();
        final String magicLinkSessionId = UUID.randomUUID().toString();
        final MagicLinkSession magicLinkSession = newMagicLinkSession(context, magicKey, magicLinkSessionId);
        final String magicLink = getMagicLink(context, magicKey, magicLinkSessionId);
        context.getAuthenticationSession().setAuthNote(MAGICLINK_SESSION_ID_KEY, magicLinkSessionId);
        if (user != null) {
            context.setUser(user);
        }
        scheduleSend(context, user == null ? null : user.getId(), magicLinkSession, magicLink);

        // Show waiting page even if user does not exist -> prevents guessing of users
        showLinkSentInfo(context);
    }

    @Override
    public void sendLink(AuthenticationFlowContext context, String magicLink) {
        // G-162: the mail goes out in the background and within the send limit.
        UserModel user = context.getUser();
        scheduleSend(context, user == null ? null : user.getId(), null, magicLink);
    }

    @Override
    public boolean requiresUser() {
        return false;
    }

    @Override
    public boolean configuredFor(KeycloakSession keycloakSession, RealmModel realmModel, UserModel userModel) {
        return true;
    }

    @Override
    public void setRequiredActions(KeycloakSession keycloakSession, RealmModel realmModel, UserModel userModel) {
        // not needed
    }

    @Override
    public void close() {
        // not needed
    }


    protected abstract String getMagicLink(AuthenticationFlowContext context, String magicKey, String magicLinkSessionId);

    protected abstract void showLinkSentInfo(AuthenticationFlowContext context);


    protected String generateMagicKey() {
        return KeycloakModelUtils.generateId();
    }

    /** Builds the row for MAGIC_LINK_SESSION. The background job writes it. */
    protected MagicLinkSession newMagicLinkSession(AuthenticationFlowContext context, String magicKey, String magicLinkSessionId) {
        AuthenticatorConfigModel config = context.getAuthenticatorConfig();
        long validityDurationInSeconds = MagicLinkValidityConstants.DEFAULT_VALIDITY_IN_SECONDS;
        if (config != null) {
            validityDurationInSeconds = Integer.parseInt(config.getConfig().get(MagicLinkValidityConstants.VALIDITY_DURATION_CONFIG_KEY));
        }

        final long validTo = Time.currentTimeMillis() + validityDurationInSeconds * 1000L;

        MagicLinkSession magicLinkSession = new MagicLinkSession();
        magicLinkSession.setId(magicLinkSessionId);
        magicLinkSession.setMagicKey(magicKey);
        magicLinkSession.setValidTo(validTo);
        magicLinkSession.setRedirectUri(context.getRefreshUrl(true).toString());
        return magicLinkSession;
    }

    /**
     * Queues the background job after the request transaction ends. The job runs for an unknown
     * address too and then stops at once, so the request does the same work in both cases.
     */
    protected void scheduleSend(AuthenticationFlowContext context, String userId, MagicLinkSession magicLinkSession, String magicLink) {
        final KeycloakSession session = context.getSession();
        final KeycloakSessionFactory factory = session.getKeycloakSessionFactory();
        final ExecutorService executor = session.getProvider(ExecutorsProvider.class).getExecutor(SEND_EXECUTOR);
        final String realmId = context.getRealm().getId();
        final AuthenticatorConfigModel config = context.getAuthenticatorConfig();
        final MagicLinkSendLimiter limiter = MagicLinkSendLimiter.fromConfig(config == null ? null : config.getConfig());
        session.getTransactionManager().enlistAfterCompletion(new AfterRequest(() -> {
            try {
                executor.execute(() -> sendInBackground(factory, realmId, userId, magicLinkSession, magicLink, limiter));
            } catch (RejectedExecutionException e) {
                logger.warn("Magic link mail not queued: the executor refused the job");
            }
        }));
    }

    private void sendInBackground(KeycloakSessionFactory factory, String realmId, String userId,
                                  MagicLinkSession magicLinkSession, String magicLink, MagicLinkSendLimiter limiter) {
        if (userId == null) {
            return;
        }
        try {
            String address = KeycloakModelUtils.runJobInTransactionWithResult(factory, s -> {
                UserModel user = findUser(s, realmId, userId);
                if (user == null) {
                    return null;
                }
                return ObjectUtil.isBlank(user.getEmail()) ? user.getUsername() : user.getEmail();
            });
            if (address == null || !limiter.tryAcquire(factory, realmId, address)) {
                return;
            }
            if (magicLinkSession != null) {
                KeycloakModelUtils.runJobInTransaction(factory,
                      s -> s.getProvider(JpaConnectionProvider.class).getEntityManager().persist(magicLinkSession));
            }
            KeycloakModelUtils.runJobInTransaction(factory, s -> {
                UserModel user = findUser(s, realmId, userId);
                if (user == null) {
                    return;
                }
                try {
                    linkSender.sendLink(s, user, magicLink);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });
        } catch (RuntimeException e) {
            // Never log the link, the key or the address.
            Throwable cause = e.getCause() == null ? e : e.getCause();
            logger.warnf("Magic link mail not sent: %s", cause.getClass().getSimpleName());
        }
    }

    private static UserModel findUser(KeycloakSession session, String realmId, String userId) {
        RealmModel realm = session.realms().getRealm(realmId);
        if (realm == null) {
            return null;
        }
        session.getContext().setRealm(realm);
        return session.users().getUserById(realm, userId);
    }

    protected EntityManager getEntityManager(AuthenticationFlowContext context) {
        return context.getSession().getProvider(JpaConnectionProvider.class).getEntityManager();
    }

    protected Response getEmailLoginForm(AuthenticationFlowContext context) {
        return context.form()
              .setAttribute(EMAIL_ATTRIBUTE_FORM_NAME, "")
              .setAuthContext(null)
              .createForm(EMAIL_INPUT_FORM_TEMPLATE);
    }

    protected String getEmailAddressInput(AuthenticationFlowContext context) {
        String email = context.getHttpRequest().getDecodedFormParameters().getFirst(EMAIL_ATTRIBUTE_FORM_NAME).trim();

        if (ObjectUtil.isBlank(email)) {
            context.failure(AuthenticationFlowError.INVALID_USER,
                  context.form().setError("Email cannot be empty").createForm(EMAIL_INPUT_FORM_TEMPLATE));
            return null;
        }
        return email;
    }

    protected UserModel findUserByEmailAddress(AuthenticationFlowContext context, String email) {
        return KeycloakModelUtils.findUserByNameOrEmail(context.getSession(), context.getRealm(), email);
    }

    protected void removeMagicLinkSession(AuthenticationFlowContext context, MagicLinkSession session) {
        EntityManager em = getEntityManager(context);
        em.getTransaction().begin();
        em.remove(session);
        em.getTransaction().commit();
    }

    /** Runs a task once, after the request transaction has committed. Does nothing on rollback. */
    private static final class AfterRequest implements KeycloakTransaction {
        private final Runnable task;
        private boolean active;
        private boolean rollbackOnly;

        private AfterRequest(Runnable task) {
            this.task = task;
        }

        @Override
        public void begin() {
            active = true;
        }

        @Override
        public void commit() {
            active = false;
            if (!rollbackOnly) {
                task.run();
            }
        }

        @Override
        public void rollback() {
            active = false;
        }

        @Override
        public void setRollbackOnly() {
            rollbackOnly = true;
        }

        @Override
        public boolean getRollbackOnly() {
            return rollbackOnly;
        }

        @Override
        public boolean isActive() {
            return active;
        }
    }
}

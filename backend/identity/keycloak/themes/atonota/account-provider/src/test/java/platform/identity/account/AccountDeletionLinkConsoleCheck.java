package platform.identity.account;

import java.util.ArrayList;
import java.util.List;

/**
 * Dependency-free checks of the two pure functions that guard the link markup.
 *
 * <p>The image build runs this class with {@code java -ea}. A failed check stops the build, so a
 * provider with a broken address or escaping rule can never be installed. The class is not part of
 * the provider jar.
 */
public final class AccountDeletionLinkConsoleCheck {

    private static final List<String> FAILURES = new ArrayList<>();

    private AccountDeletionLinkConsoleCheck() {
    }

    public static void main(String[] args) {
        // Addresses that must be accepted, with the exact value that is written into the page.
        accepts("https://press.example/account/delete", "https://press.example/account/delete");
        accepts("http://press.localhost:3953/account/delete", "http://press.localhost:3953/account/delete");
        accepts("http://localhost:8000/delete", "http://localhost:8000/delete");
        accepts("http://LOCALHOST/delete", "http://LOCALHOST/delete");
        accepts("  https://press.example/delete  ", "https://press.example/delete");
        accepts("HTTPS://Press.Example/delete", "HTTPS://Press.Example/delete");
        accepts("https://press.example/delete?next=a&lang=tr", "https://press.example/delete?next=a&lang=tr");
        accepts("https://press.example/it's", "https://press.example/it's");

        // Addresses that must be refused. No link is better than an unsafe link.
        refuses(null);
        refuses("");
        refuses("   ");
        refuses("javascript:alert(1)");
        refuses("JavaScript:alert(1)");
        refuses("data:text/html,<script>alert(1)</script>");
        refuses("vbscript:msgbox(1)");
        refuses("/account/delete");
        refuses("//evil.example/account/delete");
        refuses("http:evil.example");
        refuses("https:///no-host");
        refuses("https://user@press.example/");
        refuses("https://user:secret@press.example/");
        refuses("https://press.example\\@evil.example/");
        refuses("https://press.example/a b");
        refuses("https://press.example/a\nb");
        refuses("https://press.example/\r\nSet-Cookie: x=1");
        refuses("https://press.example/\"onmouseover=\"alert(1)");
        refuses("https://press.example/<script>");
        // Plain http is accepted only for a local development host. Everything else must use https.
        refuses("http://press.example/account/delete");
        refuses("http://localhost.evil.example/delete");
        refuses("http://notlocalhost/delete");
        refuses("http://127.0.0.1/delete");
        refuses("ftp://press.example/delete");
        refuses("file:///etc/passwd");
        // A host with an underscore or a non-ASCII letter is refused. Such a name must be written in its ASCII form.
        refuses("https://press_site.example/delete");
        refuses("https://örnek.example/delete");

        // Escaping for HTML text and for a double-quoted attribute.
        escapes("plain text", "plain text");
        escapes("a&b", "a&amp;b");
        escapes("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;");
        escapes("\" onmouseover=\"x", "&quot; onmouseover=&quot;x");
        escapes("it's", "it&#39;s");
        escapes("&amp;", "&amp;amp;");
        escapes("Hesabınızı silmek mi istiyorsunuz?", "Hesabınızı silmek mi istiyorsunuz?");

        // An accepted address stays inside its attribute after escaping.
        String written = AccountDeletionLinkConsole.escape(
                AccountDeletionLinkConsole.safeAddress("https://press.example/delete?next=a&lang=tr'x"));
        check("https://press.example/delete?next=a&amp;lang=tr&#39;x".equals(written), "attribute value: " + written);
        check(!written.contains("\"") && !written.contains("<") && !written.contains(">"), "attribute breakout: " + written);

        // The role that marks a customer is not the role of Keycloak's own delete action.
        check(!"delete-account".equals(AccountDeletionLinkConsole.CUSTOMER_ROLE), "customer role must differ from delete-account");
        check("request-account-deletion".equals(AccountDeletionLinkConsole.CUSTOMER_ROLE), "customer role name");

        if (!FAILURES.isEmpty()) {
            for (String failure : FAILURES) {
                System.err.println("FAILED: " + failure);
            }
            throw new AssertionError(FAILURES.size() + " provider check(s) failed");
        }
        System.out.println("provider checks passed");
    }

    private static void accepts(String value, String expected) {
        String actual = AccountDeletionLinkConsole.safeAddress(value);
        check(expected.equals(actual), "safeAddress(" + value + ") should be " + expected + " but was " + actual);
    }

    private static void refuses(String value) {
        String actual = AccountDeletionLinkConsole.safeAddress(value);
        check(actual == null, "safeAddress(" + value + ") should be refused but was " + actual);
    }

    private static void escapes(String value, String expected) {
        String actual = AccountDeletionLinkConsole.escape(value);
        check(expected.equals(actual), "escape(" + value + ") should be " + expected + " but was " + actual);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            FAILURES.add(message);
        }
    }
}

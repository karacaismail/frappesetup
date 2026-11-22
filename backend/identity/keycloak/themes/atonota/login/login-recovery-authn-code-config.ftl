<#--
  ATONOTA: Source Keycloak 26.8.2, keycloak.v2/login/login-recovery-authn-code-config.ftl.
  Differences:
  - The warning label comes from the message bundle. The stock template writes it in English.
  - The warning title is an h2. The stock h4 skips two heading levels (axe rule "heading-order").
  - Buttons and the checkbox are wired in the script. The stock template uses inline event attributes.
  - The date in the downloaded file uses the language of the page. The stock template always uses en-US.
-->
<#import "template.ftl" as layout>
<#import "password-commons.ftl" as passwordCommons>
<@layout.registrationLayout; section>
<#if section = "header">
    ${msg("recovery-code-config-header")}
<#elseif section = "form">
    <!-- warning -->
    <div class="${properties.kcRecoveryCodesWarning!}" role="note" aria-label="${msg("atWarningLabel")}">
        <div class="${properties.kcAlertIconClass!}">
            <i class="fas fa-fw fa-bell" aria-hidden="true"></i>
        </div>
        <h2 class="${properties.kcAlertTitleClass!}">
            <span class="pf-v5-screen-reader">${msg("atWarningLabel")}:</span>
            ${msg("recovery-code-config-warning-title")}
        </h2>
        <div class="${properties.kcAlertDescriptionClass!}">
            <p>${msg("recovery-code-config-warning-message")}</p>
        </div>
    </div>

    <div class="${properties.kcPanelClass!}">
        <div class="${properties.kcPanelMainClass!}">
            <div class="${properties.kcPanelMainBodyClass!}">
            <ol id="kc-recovery-codes-list" class="${properties.kcListClass!}" role="list">
                <#list recoveryAuthnCodesConfigBean.generatedRecoveryAuthnCodesList as code>
                    <li>${code[0..3]}-${code[4..7]}-${code[8..]}</li>
                </#list>
            </ol>
            </div>
        </div>
    </div>

    <!-- actions -->
    <div class="${properties.kcRecoveryCodesActions!}">
        <button id="printRecoveryCodes" class="${properties.kcButtonLinkClass}" type="button">
            <i class="fas fa-print" aria-hidden="true"></i> ${msg("recovery-codes-print")}
        </button>
        <button id="downloadRecoveryCodes" class="${properties.kcButtonLinkClass}" type="button">
            <i class="fas fa-download" aria-hidden="true"></i> ${msg("recovery-codes-download")}
        </button>
        <button id="copyRecoveryCodes" class="${properties.kcButtonLinkClass}" type="button">
            <i class="fas fa-copy" aria-hidden="true"></i> ${msg("recovery-codes-copy")}
        </button>
    </div>

    <!-- confirmation checkbox -->
    <div class="${properties.kcFormOptionsClass!} pf-v5-u-mt-md">
        <input class="${properties.kcCheckInputClass!}" type="checkbox" id="kcRecoveryCodesConfirmationCheck" name="kcRecoveryCodesConfirmationCheck" />
        <label for="kcRecoveryCodesConfirmationCheck">${msg("recovery-codes-confirmation-message")}</label>
    </div>

    <form action="${url.loginAction}" class="${properties.kcFormGroupClass!}" id="kc-recovery-codes-settings-form" method="post">
        <input type="hidden" name="generatedRecoveryAuthnCodes" value="${recoveryAuthnCodesConfigBean.generatedRecoveryAuthnCodesAsString}" />
        <input type="hidden" name="generatedAt" value="${recoveryAuthnCodesConfigBean.generatedAt?c}" />
        <input type="hidden" id="userLabel" name="userLabel" value="${msg("recovery-codes-label-default")}" />
        <@passwordCommons.logoutOtherSessions/>

        <#if isAppInitiatedAction??>
            <input type="submit"
            class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonLargeClass!}"
            id="saveRecoveryAuthnCodesBtn" value="${msg("recovery-codes-action-complete")}"
            disabled
            />
            <button type="submit"
                class="${properties.kcButtonClass!} ${properties.kcButtonDefaultClass!} ${properties.kcButtonLargeClass!} pf-m-link"
                id="cancelRecoveryAuthnCodesBtn" name="cancel-aia" value="true">${msg("recovery-codes-action-cancel")}
            </button>
        <#else>
            <input type="submit"
            class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
            id="saveRecoveryAuthnCodesBtn" value="${msg("recovery-codes-action-complete")}"
            disabled
            />
        </#if>
    </form>

    <script type="module">
        <#outputformat "JavaScript">
        /* copy recovery codes  */
        function copyRecoveryCodes() {
            const tmpTextarea = document.createElement("textarea");
            tmpTextarea.value = parseRecoveryCodeList();
            document.body.appendChild(tmpTextarea);
            tmpTextarea.select();
            document.execCommand("copy");
            document.body.removeChild(tmpTextarea);
        }

        /* download recovery codes  */
        function formatCurrentDateTime() {
            const dt = new Date();
            const options = {
                month: 'long',
                day: 'numeric',
                year: 'numeric',
                hour: 'numeric',
                minute: 'numeric',
                timeZoneName: 'short'
            };

            return dt.toLocaleString(document.documentElement.lang || 'tr', options);
        }

        function parseRecoveryCodeList() {
            const recoveryCodes = document.getElementById("kc-recovery-codes-list").getElementsByTagName("li");
            let recoveryCodeList = "";

            for (let i = 0; i < recoveryCodes.length; i++) {
                const recoveryCodeLiElement = recoveryCodes[i].innerText;
                <#noparse>
                recoveryCodeList += `${i+1}: ${recoveryCodeLiElement}\r\n`;
                </#noparse>
            }

            return recoveryCodeList;
        }

        function buildDownloadContent() {
            const recoveryCodeList = parseRecoveryCodeList();
            const fileBodyContent =
                ${msg("recovery-codes-download-file-header")?c} + "\n\n" +
                recoveryCodeList + "\n" +
                ${msg("recovery-codes-download-file-description")?c} + "\n\n" +
                ${msg("recovery-codes-download-file-date")?c} + " " + formatCurrentDateTime();
            return fileBodyContent;
        }

        function setUpDownloadLinkAndDownload(filename, text) {
            const el = document.createElement('a');
            el.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
            el.setAttribute('download', filename);
            el.style.display = 'none';
            document.body.appendChild(el);
            el.click();
            document.body.removeChild(el);
        }

        function downloadRecoveryCodes() {
            setUpDownloadLinkAndDownload('kc-download-recovery-codes.txt', buildDownloadContent());
        }

        function printRecoveryCodes() {
            const printWindow = window.open();
            if (!printWindow) return;

            const printDocument = printWindow.document;
            printDocument.title = 'kc-download-recovery-codes';
            printDocument.documentElement.lang = document.documentElement.lang;
            const styles = printDocument.createElement('style');
            styles.textContent = '@page { size: auto; margin-top: 0; } body { width: 480px; } ol { font-family: monospace; } p:first-of-type { margin-top: 48px; }';
            printDocument.head.append(styles);

            function paragraph(text) {
                const element = printDocument.createElement('p');
                element.textContent = text;
                return element;
            }

            printDocument.body.append(
                paragraph(${msg("recovery-codes-download-file-header")?c}),
                printDocument.importNode(document.getElementById('kc-recovery-codes-list'), true),
                paragraph(${msg("recovery-codes-download-file-description")?c}),
                paragraph(${msg("recovery-codes-download-file-date")?c} + ' ' + formatCurrentDateTime())
            );
            printWindow.print();
            printWindow.close();
        }

        document.getElementById('printRecoveryCodes').addEventListener('click', printRecoveryCodes);
        document.getElementById('downloadRecoveryCodes').addEventListener('click', downloadRecoveryCodes);
        document.getElementById('copyRecoveryCodes').addEventListener('click', copyRecoveryCodes);
        const confirmation = document.getElementById('kcRecoveryCodesConfirmationCheck');
        confirmation.addEventListener('change', () => {
            document.getElementById('saveRecoveryAuthnCodesBtn').disabled = !confirmation.checked;
        });
        </#outputformat>
    </script>
</#if>
</@layout.registrationLayout>

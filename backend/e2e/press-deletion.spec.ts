import { expect, request as apiRequest, test, type APIRequestContext } from '@playwright/test';
import { required } from './local';
import { bearer, closeSession, fixtureEmail, keycloakReaderToken, requestPressDeletion, resource, sites } from './press-session';

// MVP test 2, row 5e: the account deletion chain from Press down to the HRMS TR employee record.
// Fixture: `backend/e2e/stack seed-deletion` (docs: backend/e2e/README.md).
const REDACTED = '[REDACTED]';
const ANONYMIZE_METHOD = '/api/method/platform_core.api.identity.anonymize_user';
// Employee fields from the hrms_tr `user_data_fields` hook, grouped by the value the contract gives them.
const REDACTED_FIELDS = ['first_name', 'middle_name', 'last_name', 'employee_name', 'cell_number', 'emergency_phone_number',
  'person_to_be_contacted', 'relation', 'iban', 'bank_name', 'bank_ac_no', 'current_address', 'permanent_address', 'bio'];
const EMAIL_FIELDS = ['personal_email', 'prefered_email', 'company_email'];
const CLEARED_FIELDS = ['date_of_birth', 'blood_group', 'marital_status', 'attendance_device_id'];

async function records(request: APIRequestContext, origin: string, cookie: string, doctype: string,
  filters: unknown[], fields: string[]) {
  const response = await request.get(origin + '/api/resource/' + encodeURIComponent(doctype), {
    params: { filters: JSON.stringify(filters), fields: JSON.stringify(fields) },
    headers: { Cookie: cookie }, maxRedirects: 0,
  });
  expect(response.status(), doctype).toBe(200);
  return (await response.json()).data as Record<string, unknown>[];
}

test.describe('Press account deletion with HRMS TR', () => {
  test.skip(() => process.env.E2E_PRESS_DELETION !== '1',
    'Requires the stack deletion fixture: backend/e2e/stack seed-deletion.');

  test('customer self-deletion on Press anonymizes the tenant user and the employee record', async ({ page, request }) => {
    test.setTimeout(180_000);
    const { tenant, press, identity } = sites();
    const email = fixtureEmail('E2E_DELETE_EMAIL', 'delete');
    const password = required('E2E_DELETE_PASSWORD');
    const subject = required('E2E_DELETE_SUBJECT');
    const employee = required('E2E_DELETE_EMPLOYEE');
    const tenantReader = required('E2E_DELETE_TENANT_READER_COOKIE');
    const pressReader = required('E2E_DELETE_PRESS_READER_COOKIE');
    const tenantAnonymous = required('E2E_DELETE_TENANT_ANONYMOUS_USER');
    const pressAnonymous = required('E2E_DELETE_PRESS_ANONYMOUS_USER');
    const serviceToken = required('E2E_DELETE_SERVICE_TOKEN');
    const issuer = identity + '/realms/platform';
    const readerToken = await keycloakReaderToken(request);
    const keycloakUser = () => request.get(identity + '/admin/realms/platform/users/' + encodeURIComponent(subject), {
      headers: bearer(readerToken), maxRedirects: 0,
    });
    const userStatus = async (origin: string, cookie: string, name: string) =>
      (await request.get(origin + '/api/resource/User/' + encodeURIComponent(name), {
        headers: { Cookie: cookie }, maxRedirects: 0,
      })).status();

    try {
      // Before: the account is open everywhere and the employee carries personal data.
      const account = await keycloakUser();
      expect(account.status()).toBe(200);
      expect((await account.json()).email).toBe(email);
      expect((await resource(request, tenant, tenantReader, 'User', email)).enabled).toBe(1);
      expect((await resource(request, press, pressReader, 'User', email)).enabled).toBe(1);
      const before = await resource(request, tenant, tenantReader, 'Employee', employee);
      expect(before.user_id).toBe(email);
      expect(before.status).toBe('Active');
      for (const field of [...REDACTED_FIELDS, ...EMAIL_FIELDS, ...CLEARED_FIELDS]) {
        expect(before[field], field).toBeTruthy();
        expect(before[field], field).not.toBe(REDACTED);
      }
      expect(EMAIL_FIELDS.map((field) => before[field])).not.toContain(tenantAnonymous);
      expect(await records(request, tenant, tenantReader, 'Platform Identity Deletion',
        [['user', 'in', [email, tenantAnonymous]]], ['state'])).toEqual([]);

      // The customer asks for the deletion on Press and confirms it with a fresh Keycloak login.
      expect(await requestPressDeletion(page, email, password)).toMatchObject({ submitted: true });

      // The sync service runs an ordered plan and deletes the Keycloak user last. A missing user shows
      // that the Press and tenant steps finished. The tenant reads below prove what they did.
      await expect.poll(async () => (await keycloakUser()).status(), { timeout: 90_000 }).toBe(404);

      // O-44, read directly: the tenant answers the sync service's call with 200 and the full result.
      // A repeated call after the work is done returns the same body (identity contract).
      // A service request must carry no session cookie, so it uses a context without a cookie jar.
      const service = await apiRequest.newContext();
      try {
        const reply = await service.post(tenant + ANONYMIZE_METHOD, {
          headers: bearer(serviceToken), data: { issuer, subject }, maxRedirects: 0,
        });
        expect(reply.status()).toBe(200);
        expect((await reply.json()).message).toEqual({
          anonymized: true, found: true, user: tenantAnonymous, enabled: false, status: 'Anonymized',
        });
      } finally {
        await service.dispose();
      }

      // Tenant: the user is renamed and disabled, the deletion record is final and the raw identity link is gone.
      expect(await userStatus(tenant, tenantReader, email)).toBe(404);
      expect((await resource(request, tenant, tenantReader, 'User', tenantAnonymous)).enabled).toBe(0);
      expect(await records(request, tenant, tenantReader, 'Platform Identity Deletion',
        [['user', '=', tenantAnonymous]], ['state'])).toEqual([{ state: 'Anonymized' }]);
      expect(await records(request, tenant, tenantReader, 'PLT Identity Link',
        [['user', 'in', [email, tenantAnonymous]]], ['name'])).toEqual([]);

      // Tenant: the employee keeps its record without the person.
      const after = await resource(request, tenant, tenantReader, 'Employee', employee);
      expect(after.user_id).toBe(tenantAnonymous);
      expect(after.status).toBe('Active');
      expect(after.company).toBe(before.company);
      for (const field of REDACTED_FIELDS) expect(after[field], field).toBe(REDACTED);
      for (const field of EMAIL_FIELDS) expect(after[field], field).toBe(tenantAnonymous);
      for (const field of CLEARED_FIELDS) expect(after[field], field).toBeFalsy();

      // Press: the user is renamed and disabled too.
      expect(await userStatus(press, pressReader, email)).toBe(404);
      expect((await resource(request, press, pressReader, 'User', pressAnonymous)).enabled).toBe(0);
    } finally {
      // The fixture's reader sessions are for this run only.
      await closeSession(request, tenant, tenantReader);
      await closeSession(request, press, pressReader);
    }
  });
});

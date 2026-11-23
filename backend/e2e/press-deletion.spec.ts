import { expect, request as apiRequest, test, type APIRequestContext } from '@playwright/test';
import { required } from './local';
import { bearer, closeSession, fixtureEmail, keycloakReaderToken, requestPressDeletion, resource, sites } from './press-session';

// MVP test 2, row 5e: the account deletion chain from Press down to the HRMS TR employee record.
// Fixture: `backend/e2e/stack seed-deletion` (docs: backend/e2e/README.md). Both tests use one fixture:
// the negative test only reads, the positive test consumes the account.
const REDACTED = '[REDACTED]';
const ANONYMIZE_METHOD = '/api/method/platform_core.api.identity.anonymize_user';
const DELETION_RECORD = 'Platform Identity Deletion';
// Employee fields from the hrms_tr `user_data_fields` hook, grouped by the value the contract gives them.
const REDACTED_FIELDS = ['first_name', 'middle_name', 'last_name', 'employee_name', 'cell_number', 'emergency_phone_number',
  'person_to_be_contacted', 'relation', 'iban', 'bank_name', 'bank_ac_no', 'current_address', 'permanent_address', 'bio'];
const EMAIL_FIELDS = ['personal_email', 'prefered_email', 'company_email'];
const CLEARED_FIELDS = ['date_of_birth', 'blood_group', 'marital_status', 'attendance_device_id'];

function fixture() {
  return {
    email: fixtureEmail('E2E_DELETE_EMAIL', 'delete'),
    employee: required('E2E_DELETE_EMPLOYEE'),
    tenantReader: required('E2E_DELETE_TENANT_READER_COOKIE'),
    tenantAnonymous: required('E2E_DELETE_TENANT_ANONYMOUS_USER'),
  };
}

async function records(request: APIRequestContext, origin: string, cookie: string, doctype: string,
  filters: unknown[], fields: string[]) {
  const response = await request.get(origin + '/api/resource/' + encodeURIComponent(doctype), {
    params: { filters: JSON.stringify(filters), fields: JSON.stringify(fields) },
    headers: { Cookie: cookie }, maxRedirects: 0,
  });
  expect(response.status(), doctype).toBe(200);
  return (await response.json()).data as Record<string, unknown>[];
}

async function userStatus(request: APIRequestContext, origin: string, cookie: string, name: string) {
  const response = await request.get(origin + '/api/resource/User/' + encodeURIComponent(name), {
    headers: { Cookie: cookie }, maxRedirects: 0,
  });
  return response.status();
}

/**
 * Read-only proof of the tenant step of the deletion flow. Nothing here can change the tenant,
 * so a sync service that skipped the tenant cannot pass these checks. Returns the deletion record.
 */
async function expectTenantAnonymized(request: APIRequestContext, { email, employee, tenantReader, tenantAnonymous }: ReturnType<typeof fixture>) {
  const { tenant } = sites();
  const deletion = await records(request, tenant, tenantReader, DELETION_RECORD,
    [['user', '=', tenantAnonymous]], ['name', 'state', 'deleted_at']);
  expect(deletion, `${DELETION_RECORD} record of the anonymous user`).toHaveLength(1);
  expect(deletion[0].state).toBe('Anonymized');
  expect(deletion[0].deleted_at).toBeTruthy();
  expect(await userStatus(request, tenant, tenantReader, email)).toBe(404);
  expect((await resource(request, tenant, tenantReader, 'User', tenantAnonymous)).enabled).toBe(0);
  expect(await records(request, tenant, tenantReader, 'PLT Identity Link',
    [['user', 'in', [email, tenantAnonymous]]], ['name'])).toEqual([]);
  const after = await resource(request, tenant, tenantReader, 'Employee', employee);
  expect(after.user_id).toBe(tenantAnonymous);
  expect(after.status).toBe('Active');
  for (const field of REDACTED_FIELDS) expect(after[field], field).toBe(REDACTED);
  for (const field of EMAIL_FIELDS) expect(after[field], field).toBe(tenantAnonymous);
  for (const field of CLEARED_FIELDS) expect(after[field], field).toBeFalsy();
  return deletion;
}

test.describe('Press account deletion with HRMS TR', () => {
  test.skip(() => process.env.E2E_PRESS_DELETION !== '1',
    'Requires the stack deletion fixture: backend/e2e/stack seed-deletion.');

  test('a sync service that skips the tenant step cannot pass the tenant checks', async ({ request }) => {
    // The fresh fixture is the tenant exactly as a skipped tenant step would leave it:
    // open user, full employee record, no deletion record. The read-only checks must fail here.
    const settings = fixture();
    const { tenant } = sites();
    expect((await resource(request, tenant, settings.tenantReader, 'User', settings.email)).enabled).toBe(1);
    // The record read itself must succeed (200) and be empty. A permission error would also mention
    // the record name, so it is ruled out here before the combined checks are expected to fail.
    expect(await records(request, tenant, settings.tenantReader, DELETION_RECORD,
      [['user', 'in', [settings.email, settings.tenantAnonymous]]], ['state'])).toEqual([]);
    await expect(expectTenantAnonymized(request, settings)).rejects.toThrow(DELETION_RECORD + ' record of the anonymous user');
    expect((await resource(request, tenant, settings.tenantReader, 'Employee', settings.employee)).first_name).not.toBe(REDACTED);
  });

  test('customer self-deletion on Press anonymizes the tenant user and the employee record', async ({ page, request }) => {
    test.setTimeout(180_000);
    const { tenant, press, identity } = sites();
    const settings = fixture();
    const { email, employee, tenantReader, tenantAnonymous } = settings;
    const password = required('E2E_DELETE_PASSWORD');
    const subject = required('E2E_DELETE_SUBJECT');
    const pressReader = required('E2E_DELETE_PRESS_READER_COOKIE');
    const pressAnonymous = required('E2E_DELETE_PRESS_ANONYMOUS_USER');
    const serviceToken = required('E2E_DELETE_SERVICE_TOKEN');
    const readerToken = await keycloakReaderToken(request);
    const keycloakUser = () => request.get(identity + '/admin/realms/platform/users/' + encodeURIComponent(subject), {
      headers: bearer(readerToken), maxRedirects: 0,
    });
    const closed: number[] = [];

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
      expect(await records(request, tenant, tenantReader, DELETION_RECORD,
        [['user', 'in', [email, tenantAnonymous]]], ['state'])).toEqual([]);

      // The customer asks for the deletion on Press and confirms it with a fresh Keycloak login.
      expect(await requestPressDeletion(page, email, password)).toMatchObject({ submitted: true });

      // The sync service runs an ordered plan and deletes the Keycloak user last.
      await expect.poll(async () => (await keycloakUser()).status(), { timeout: 90_000 }).toBe(404);

      // Read-only proof first: the service's own tenant step left the record, closed the user,
      // removed the identity link and anonymized the employee. Only reads happen before this point.
      const deletion = await expectTenantAnonymized(request, settings);
      expect((await resource(request, tenant, tenantReader, 'Employee', employee)).company).toBe(before.company);

      // Press: the user is renamed and disabled too.
      expect(await userStatus(request, press, pressReader, email)).toBe(404);
      expect((await resource(request, press, pressReader, 'User', pressAnonymous)).enabled).toBe(0);

      // Repeat-call contract last: a second call for a finished deletion returns 200 with the
      // same O-44 body and opens no new record. A service request carries no session cookie,
      // so it uses a context without a cookie jar.
      const service = await apiRequest.newContext();
      try {
        const reply = await service.post(tenant + ANONYMIZE_METHOD, {
          headers: bearer(serviceToken), data: { issuer: identity + '/realms/platform', subject }, maxRedirects: 0,
        });
        expect(reply.status()).toBe(200);
        expect((await reply.json()).message).toEqual({
          anonymized: true, found: true, user: tenantAnonymous, enabled: false, status: 'Anonymized',
        });
      } finally {
        await service.dispose();
      }
      expect(await records(request, tenant, tenantReader, DELETION_RECORD,
        [['user', '=', tenantAnonymous]], ['name', 'state', 'deleted_at'])).toEqual(deletion);
    } finally {
      // The fixture's reader sessions are for this run only. A close that fails must not hide the
      // real failure, so the results are checked after the test body.
      closed.push(await closeSession(request, tenant, tenantReader));
      closed.push(await closeSession(request, press, pressReader));
    }
    expect(closed, 'fixture sessions closed').toEqual([200, 200]);
  });
});

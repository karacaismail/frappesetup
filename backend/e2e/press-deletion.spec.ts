import { expect, test } from '@playwright/test';
import { required } from './local';
import { bearer, fixtureEmail, keycloakReaderToken, requestPressDeletion, resource, sites } from './press-session';

// MVP test 2, row 5e: the account deletion chain from Press down to the HRMS TR employee record.
// Fixture: `backend/e2e/stack seed-deletion` (docs: backend/e2e/README.md).
const REDACTED = '[REDACTED]';
// Employee fields from the hrms_tr `user_data_fields` hook, grouped by the value the contract gives them.
const REDACTED_FIELDS = ['first_name', 'middle_name', 'last_name', 'employee_name', 'cell_number', 'emergency_phone_number',
  'person_to_be_contacted', 'relation', 'iban', 'bank_name', 'bank_ac_no', 'current_address', 'permanent_address', 'bio'];
const EMAIL_FIELDS = ['personal_email', 'prefered_email', 'company_email'];
const CLEARED_FIELDS = ['date_of_birth', 'blood_group', 'marital_status', 'attendance_device_id'];

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
    const readerToken = await keycloakReaderToken(request);
    const keycloakUser = () => request.get(identity + '/admin/realms/platform/users/' + encodeURIComponent(subject), {
      headers: bearer(readerToken), maxRedirects: 0,
    });
    const userStatus = async (origin: string, cookie: string, name: string) =>
      (await request.get(origin + '/api/resource/User/' + encodeURIComponent(name), {
        headers: { Cookie: cookie }, maxRedirects: 0,
      })).status();

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

    // The customer asks for the deletion on Press and confirms it with a fresh Keycloak login.
    expect(await requestPressDeletion(page, email, password)).toMatchObject({ submitted: true });

    // The sync service deletes the Keycloak user only after Press and the tenant answered
    // 200 with `anonymized: true` and `found: true` (O-43, O-44). A missing user proves that reply.
    await expect.poll(async () => (await keycloakUser()).status(), { timeout: 90_000 }).toBe(404);

    // Tenant: the user is renamed and disabled, the employee keeps its record without the person.
    expect(await userStatus(tenant, tenantReader, email)).toBe(404);
    expect((await resource(request, tenant, tenantReader, 'User', tenantAnonymous)).enabled).toBe(0);
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
  });
});

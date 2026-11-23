import { request } from '@playwright/test';

function mobileHeaders(token: string | undefined, installation: string) {
  return {
    ...(token ? { Authorization: 'Bearer ' + token } : {}),
    'X-Platform-Installation': installation,
    'X-Mobile-App-Version': '1.0.0',
    'X-Mobile-Contract-Version': '1',
  };
}

export async function postMobile(
  methods: string, method: string, token: string | undefined, installation: string,
  data = {}, sessionCookie?: string,
  // v1_cleanup rejects an installation_id body field; pass { installationField: false } there.
  { installationField = true }: { installationField?: boolean } = {},
) {
  // Each phone request starts without the cookies returned by the preceding response.
  const context = await request.newContext();
  try {
    const response = await context.post(methods + 'platform_core.api.mobile.v1_' + method, {
      maxRedirects: 0,
      headers: { ...mobileHeaders(token, installation), ...(sessionCookie ? { Cookie: sessionCookie } : {}) },
      data: installationField ? { installation_id: installation, ...data } : data,
    });
    const body = await response.text();
    return { status: response.status(), json: () => JSON.parse(body) };
  } finally {
    await context.dispose();
  }
}

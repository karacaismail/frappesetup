/** @typedef {{ PRODUCT_NAME: string, BRAND_DOMAIN: string }} Brand */

/** Read the public, unquoted KEY=value format shared with deployment. */
export function parseBrand(source) {
  const values = {};
  const keys = ['PRODUCT_NAME', 'BRAND_DOMAIN'];
  for (const raw of source.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const separator = line.indexOf('=');
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    if (separator < 0 || !keys.includes(key) || Object.hasOwn(values, key)) {
      throw new Error('brand.env: expected each supported key exactly once');
    }
    if (!value || /[\u0000-\u001f\u007f]/.test(value) || /^['"]|['"]$/.test(value)) {
      throw new Error(`brand.env: ${key} must be a nonempty unquoted value`);
    }
    values[key] = value;
  }
  if (keys.some(key => !Object.hasOwn(values, key))) throw new Error('brand.env: missing required key');
  const labels = values.BRAND_DOMAIN.split('.');
  // Match the shared deployment reader's allowance for generated subdomains.
  if (values.BRAND_DOMAIN.length > 238 || labels.length < 2 || labels.some(label =>
    !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(label))) {
    throw new Error('brand.env: BRAND_DOMAIN must be a bare DNS domain');
  }
  return /** @type {Brand} */ (values);
}

/** @param {string} text @param {Brand} brand */
export function fillBrand(text, brand) {
  return text.replace(/\{\{(PRODUCT_NAME|BRAND_DOMAIN)\}\}/g, (_, key) => brand[key]);
}

/** Resolve presentation strings while keeping the source data immutable.
 * @template T
 * @param {T} data
 * @param {Brand} brand
 * @returns {T}
 */
export function fillBrandData(data, brand) {
  if (typeof data === 'string') return /** @type {T} */ (fillBrand(data, brand));
  if (Array.isArray(data)) return /** @type {T} */ (data.map(value => fillBrandData(value, brand)));
  if (data && typeof data === 'object') {
    return /** @type {T} */ (Object.fromEntries(Object.entries(data).map(([key, value]) => [key, fillBrandData(value, brand)])));
  }
  return data;
}

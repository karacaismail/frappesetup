// Site-wide constants — single source; Site.astro, index.astro and the components read from here.
import brandSource from '../../backend/brand.env?raw';
import { parseBrand, fillBrand as fill, fillBrandData as fillData } from '../lib/brand.mjs';
const brand = parseBrand(brandSource);
export const { PRODUCT_NAME, BRAND_DOMAIN } = brand;
export const fillBrand = (text: string): string => fill(text, brand);
export const fillBrandData = <T,>(data: T): T => fillData(data, brand);
export const SITE_TITLE = 'frappesetup';
export const SITE_TAGLINE = 'Frappe Headless SaaS — mimari karar çerçevesi';
// The day the site was last synced with backend. Updated by hand when content changes; tests/as-of.spec.ts checks it.
export const AS_OF = '27 Kasım 2026';
export const REPO_URL = 'https://github.com/karacaismail/frappesetup';
export const DECISION_COUNT = 10;
export const RAIL_COUNT = 6;

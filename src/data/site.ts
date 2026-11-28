// Site genel sabitleri — tek kaynak; Site.astro, index.astro ve bileşenler buradan okur.
import brandSource from '../../backend/brand.env?raw';
import { parseBrand, fillBrand as fill, fillBrandData as fillData } from '../lib/brand.mjs';
const brand = parseBrand(brandSource);
export const { PRODUCT_NAME, BRAND_DOMAIN } = brand;
export const fillBrand = (text: string): string => fill(text, brand);
export const fillBrandData = <T,>(data: T): T => fillData(data, brand);
export const SITE_TITLE = 'frappesetup';
export const SITE_TAGLINE = 'Frappe Headless SaaS — mimari karar çerçevesi';
// Sitenin backend ile son eşitlendiği gün. İçerik değişince elle güncellenir; tests/as-of.spec.ts denetler.
export const AS_OF = '28 Kasım 2026';
export const REPO_URL = 'https://github.com/karacaismail/frappesetup';
export const DECISION_COUNT = 10;
export const RAIL_COUNT = 6;

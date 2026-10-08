import phases from './phases.json';

// Site genel sabitleri — tek kaynak; Site.astro, index.astro ve bileşenler buradan okur.
export const SITE_TITLE = 'frappesetup';
export const SITE_TAGLINE = 'Frappe Headless SaaS — mimari karar çerçevesi';
export const AS_OF = '8 Ekim 2026';
export const REPO_URL = 'https://github.com/karacaismail/frappesetup';
// Plan uzunluğu fazların en geç bitişidir (phases.json tek kaynak).
export const ROADMAP_WEEKS = Math.max(...phases.map((p) => p.end));
export const DECISION_COUNT = 10;
export const RAIL_COUNT = 6;

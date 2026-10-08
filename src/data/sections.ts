// Bölüm üst verisi: navigasyon grubu, ikon adı ve tek cümlelik özet.
// İçeriğin kendisi src/content/docs içindedir; burada yalnızca sunum bilgisi tutulur.
export type IconName =
  | 'home'
  | 'scale'
  | 'route'
  | 'server'
  | 'settings'
  | 'code'
  | 'layout'
  | 'key'
  | 'sparkles'
  | 'headset'
  | 'list'
  | 'sidebar'
  | 'apps'
  | 'map'
  | 'alert'
  | 'shield'
  | 'link'
  | 'chart'
  | 'help'
  | 'checklist'
  | 'plug'
  | 'book'
  | 'robot'
  | 'tools'
  | 'file';

export interface SectionMeta {
  group: 'Çerçeve' | 'Raylar' | 'Sözleşmeler' | 'Teslim' | 'AI';
  icon: IconName;
  summary: string;
}

export const GROUP_ORDER: SectionMeta['group'][] = ['Çerçeve', 'Raylar', 'Sözleşmeler', 'Teslim', 'AI'];

// Kenar çubuğunda açılır-kapanır tek bir üst öğe olarak çizilen gruplar (grup adı → ikon).
export const COLLAPSIBLE_GROUPS: Record<string, IconName> = { AI: 'sparkles' };

export const SECTIONS: Record<string, SectionMeta> = {
  kararlar: { group: 'Çerçeve', icon: 'scale', summary: 'On sabit karar, kapsam sınırı ve roller.' },
  raylar: { group: 'Çerçeve', icon: 'route', summary: 'Altı rayın sahiplik, sözleşme ve tüketim sınırları.' },
  'karar-katalogu': {
    group: 'Çerçeve',
    icon: 'checklist',
    summary: 'Araştırma notlarından çıkan kimlik, AI, arayüz ve kalite kararları; çelişkiler açık kararlara bağlı.',
  },
  'rail-1-press': { group: 'Raylar', icon: 'server', summary: 'Abonelik, plan, marketplace, iyzico ve ödeme planı.' },
  'rail-2-yapilandirma': { group: 'Raylar', icon: 'settings', summary: 'Kiracı site yapılandırması ve Türkiye temel çizgisi.' },
  'rail-2-gelistirme': { group: 'Raylar', icon: 'code', summary: 'platform_core: Access Rule motoru, meta API, outbox.' },
  'rail-3-frontend': { group: 'Raylar', icon: 'layout', summary: 'Headless panel, metadata-driven CRUD ve shell.' },
  'rail-4-keycloak': { group: 'Raylar', icon: 'key', summary: "Realm, client'lar, SSO/SLO ve identity-sync." },
  'rail-5-ai': { group: 'Raylar', icon: 'sparkles', summary: 'Agent servisi, MCP, önizle + onayla, KVKK.' },
  'rail-6-operasyon': { group: 'Raylar', icon: 'headset', summary: 'Superadmin, CRM/Helpdesk, muhasebe ve destek oturumu.' },
  'kalite-kurallari': {
    group: 'Sözleşmeler',
    icon: 'shield',
    summary: 'Güvenlik, performans ve sürdürülebilirlik için MUST/SHOULD/MAY kuralları.',
  },
  'paylasim-url': {
    group: 'Sözleşmeler',
    icon: 'link',
    summary: 'İnsan odaklı URL, paylaşım bağlantıları ve kapalı panel için güvenli önizleme.',
  },
  'olcum-gozlem': {
    group: 'Sözleşmeler',
    icon: 'chart',
    summary: 'Ölçüm adapterları, rıza kapısı, BI ve gözlemlenebilirlik rolleri.',
  },
  'yardim-tur': {
    group: 'Sözleşmeler',
    icon: 'help',
    summary: 'Yardım kulakçığı, kendi kendine destek modu, tur ve keşif motoru.',
  },
  gereksinimler: { group: 'Teslim', icon: 'list', summary: 'G ve SA serisi gereksinimlerin ana listesi, süzülebilir gezgin.' },
  'admin-shell': { group: 'Teslim', icon: 'sidebar', summary: 'Her SaaS admin shell için olmazsa olmazlar.' },
  'app-cercevesi': { group: 'Teslim', icon: 'apps', summary: 'Satılan her app için çerçeve şablonu.' },
  'yol-haritasi': { group: 'Teslim', icon: 'map', summary: 'P0–P6 fazları, kapılar ve ilk dikey dilim.' },
  'acik-kararlar': { group: 'Teslim', icon: 'alert', summary: 'Açık kararlar, riskler ve dış bağımlılıklar.' },
  izlenebilirlik: {
    group: 'Teslim',
    icon: 'checklist',
    summary: 'Değerlendirme raporu maddelerinin kapanışı ve kaynak defteri.',
  },
  'ai-bakis': { group: 'AI', icon: 'sparkles', summary: 'Hazır depolar nasıl kullanılır; üç katmanlı AI yığını ve karar özeti.' },
  'ai-mcp': { group: 'AI', icon: 'plug', summary: 'Resmi ve topluluk MCP sunucuları: araçlar, kimlik, güvenlik, boşluklar.' },
  'ai-skills': { group: 'AI', icon: 'book', summary: 'Resmi ve topluluk skill paketleri: kapsam, kalite, v16 durumu.' },
  'ai-agents': { group: 'AI', icon: 'robot', summary: 'Frappe içi AI asistan ve ajan uygulamaları: mimari, güvenlik, olgunluk.' },
  'ai-press-yetkinlik': { group: 'AI', icon: 'server', summary: 'Press kılavuzundaki işlemler hangi araçla yapılabilir? Kanıtlı yetkinlik matrisi.' },
  'ai-gelistirme': { group: 'AI', icon: 'tools', summary: 'Kendi skill, MCP ve ajanlarınızı geliştirme planı; öncelik, tasarım, kabul ölçütü.' },
};

export const RAILS = [
  { n: 1, name: 'Press', detail: 'Frappe v15 · Python 3.11', slug: 'rail-1-press' },
  { n: 2, name: 'Kiracı siteleri', detail: 'ERPNext v16 · Frappe v16', slug: 'rail-2-yapilandirma' },
  { n: 3, name: 'Headless panel', detail: 'React · Ant Design · TanStack', slug: 'rail-3-frontend' },
  { n: 4, name: 'Keycloak', detail: 'OIDC · Organizations · MFA', slug: 'rail-4-keycloak' },
  { n: 5, name: 'AI', detail: 'Claude Agent SDK · MCP', slug: 'rail-5-ai' },
  { n: 6, name: 'Operasyon', detail: 'ERPNext · CRM · Helpdesk', slug: 'rail-6-operasyon' },
];

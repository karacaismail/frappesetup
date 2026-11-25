import { expect, test } from '@playwright/test';
import { BRAND, screen } from './helpers';

// Screens that had no test before (project record, technical debt "some theme screens are not tested").
// Layout, text size, font, control size and axe run for these screens through the shared screen list
// (layout.spec.ts and accessibility.spec.ts). This file checks what the user reads: plain Turkish,
// full sentences, the formal "siz" address and no leftover English.

type Expectation = { title: string; texts: string[]; buttons?: string[]; links?: string[] };

const expected: Record<string, Expectation> = {
  'update-profile': {
    title: 'Hesap bilgilerinizi güncelleyin',
    texts: ['Devam etmek için hesap bilgilerinizi güncelleyin.'],
    buttons: ['Gönderin'],
  },
  'recovery-codes-setup': {
    title: 'Kurtarma kodlarınız',
    texts: [
      'Kurtarma kodu, telefonunuza ulaşamadığınızda oturum açmanızı sağlar. Devam etmek için kodlarınızı kaydedin.',
      'Bu kodları bir daha göremezsiniz.',
      'Kodları yazdırın, indirin ya da kopyalayın. Sonra güvenli bir yerde saklayın. Kurulumdan vazgeçerseniz bu kodlar silinir.',
      'Kodları güvenli bir yere kaydettim',
    ],
    buttons: ['Yazdırın', 'İndirin', 'Kopyalayın', 'Kurulumu tamamlayın'],
  },
  'delete-credential': {
    title: 'Telefon silinsin mi?',
    texts: ['Telefon adlı giriş yöntemi silinecek. Onaylıyor musunuz?'],
    buttons: ['Silmeyi onaylayın', 'Vazgeçin'],
  },
  'sign-out-confirm': {
    title: 'Oturumu kapatma',
    texts: [
      'Hangi oturumu kapatmak istiyorsunuz?',
      'Bu oturum',
      'Yalnız bu cihazdaki oturum kapanır. Öteki cihazlarda oturum açık kalır.',
      'Başka bir oturum',
      'Cihazlar sayfası açılır. Kapatmak istediğiniz cihazın yanındaki “Oturumu kapatın” düğmesine basın. Başka cihazda oturum yoksa sayfada düğme görünmez.',
      'Bütün cihazlar',
      'Cihazlar sayfası açılır. Orada “Bütün cihazlarda oturumu kapatın” düğmesine basın. Bu cihazdaki oturum da kapanır. Başka cihazda oturum yoksa düğme görünmez.',
    ],
    buttons: ['Bu oturumu kapatın'],
    links: ['Başka bir oturumu kapatın', 'Bütün cihazlarda oturumu kapatın'],
  },
  'signed-out': {
    title: 'Oturumu kapattınız',
    texts: ['Oturumu kapattınız'],
  },
  error: {
    title: 'Bir sorun oldu',
    texts: ['Bu bağlantı çalışmıyor. Uygulamaya dönüp yeniden deneyin.'],
  },
  'page-expired': {
    title: 'Sayfanın süresi doldu',
    texts: ['Bu sayfanın süresi doldu. Ne yapmak istersiniz?'],
    links: ['Baştan başlayın', 'Kaldığınız yerden devam edin'],
  },
};

for (const [name, want] of Object.entries(expected)) {
  test(`${name}: the screen is themed and reads in plain Turkish`, async ({ page }) => {
    await screen(name).open(page);
    await expect(page.locator('.at-brand')).toContainText(BRAND);
    expect(await page.locator('link[href*="css/atonota.css"]').count(), 'theme stylesheet').toBe(1);
    await expect(page.locator('#kc-page-title')).toHaveText(want.title);
    const main = page.locator('main, #kc-content').first();
    for (const control of await main.locator('[tabindex]').all()) {
      expect(Number(await control.getAttribute('tabindex')), 'natural tab order').toBeLessThanOrEqual(0);
    }
    for (const text of want.texts) await expect(main, text).toContainText(text);
    for (const button of want.buttons ?? []) await expect(page.getByRole('button', { name: button, exact: true }), button).toBeVisible();
    for (const link of want.links ?? []) await expect(page.getByRole('link', { name: link, exact: true }), link).toBeVisible();

    // No leftover from the stock translation: a label that ends with a comma, or English helper text.
    const pieces = await main.evaluate((root) => {
      const found: string[] = [];
      for (const element of root.querySelectorAll('*')) {
        if (element.matches('script, style')) continue;
        for (const node of element.childNodes) if (node.nodeType === Node.TEXT_NODE && node.textContent!.trim()) found.push(node.textContent!.trim());
        for (const attribute of ['aria-label', 'title', 'placeholder', 'alt']) {
          const value = element.getAttribute(attribute);
          if (value?.trim()) found.push(value.trim());
        }
      }
      return found;
    });
    expect(pieces.filter((piece) => /[,;]$/.test(piece)), 'texts that end with a comma').toEqual([]);
    expect(pieces.filter((piece) => /\b(Warning|alert|Submit|Cancel|Delete|Logout|Recovery)\b/.test(piece)), 'English leftovers').toEqual([]);
    // The theme speaks to "siz". The informal imperative of the stock translation must not appear on a button.
    const buttons = await main.locator('button, input[type=submit], a.pf-v5-c-button').evaluateAll((elements) => elements.map((element) => ((element as HTMLInputElement).value || element.textContent || '').trim()).filter(Boolean));
    expect(buttons.filter((label) => /^(Sil|Gönder|Reddet|Yazdır|İndir|Kopyala|İptal et|Oturumu kapat|Onayla)$/.test(label)), 'informal button labels').toEqual([]);
  });
}

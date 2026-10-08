import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  Anchor,
  AppShell,
  Box,
  Burger,
  Group,
  MantineProvider,
  Stack,
  Text,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconBrandGithub, IconMoon, IconSun } from '@tabler/icons-react';
import { cssVariablesResolver, theme } from '../theme';
import { sectionIcon } from './icons';

export interface NavItem {
  href: string;
  label: string;
  order: number;
  group: string;
  icon: string;
}

export interface Heading {
  depth: number;
  slug: string;
  text: string;
}

interface ShellProps {
  nav: NavItem[];
  current: string;
  homeHref: string;
  repoUrl: string;
  headings?: Heading[];
  asOf: string;
  children?: ReactNode;
}

// Yerleşim sabitleri (px): AppShell bunları CSS değişkenlerine çevirir; global.css --fs-header-h ile eşleşir.
// Kabuk JS bütçesi (AGENTS.md): yalnız kabuğun gerçekten gerektirdiği Mantine bileşenleri kullanılır; gezinme bağlantısı
// ve simge düğmeleri sade öğelerdir ve aynı tokenlarla global.css'te çizilir (Tooltip/ScrollArea/NavLink/ActionIcon yok).
const HEADER_HEIGHT = 60;
const NAVBAR_WIDTH = 280;
const ASIDE_WIDTH = 248;

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  // 'auto' tercih (kayıt yok) işletim sistemi şemasına çözülür; ilk değer efektte okunur, SSR çıktısıyla aynı başlar.
  const computed = useComputedColorScheme('light', { getInitialValueInEffect: true });
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = mounted && computed === 'dark';
  const label = dark ? 'Açık temaya geç' : 'Koyu temaya geç';
  return (
    <button
      type="button"
      className="icon-btn"
      aria-label={label}
      title={label}
      data-testid="color-scheme-toggle"
      onClick={() => setColorScheme(dark ? 'light' : 'dark')}
    >
      {dark ? <IconSun size={20} aria-hidden /> : <IconMoon size={20} aria-hidden />}
    </button>
  );
}

// Sayfadaki h2'leri izler; okuma çizgisini (başlık altı) geçen son bölümü "Bu sayfada" listesinde vurgular.
// Kaydırma tabanlı ve deterministiktir (IntersectionObserver'ın tarayıcılar arası ilk-geri çağrı farkları yok).
function useScrollSpy(slugs: string[]) {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    if (slugs.length === 0) return;
    const els = slugs
      .map((s) => document.getElementById(s))
      .filter((el): el is HTMLElement => Boolean(el));
    if (els.length === 0) return;
    let ticking = false;
    const compute = () => {
      ticking = false;
      const line = HEADER_HEIGHT + 24;
      const doc = document.documentElement;
      const atBottom = doc.scrollTop + doc.clientHeight >= doc.scrollHeight - 2;
      let current: HTMLElement | null = null;
      for (const el of els) {
        if (el.getBoundingClientRect().top <= line) current = el;
        else break;
      }
      if (atBottom) current = els[els.length - 1];
      setActive((current ?? els[0]).id);
    };
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(compute);
      }
    };
    compute();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [slugs.join('|')]);
  return active;
}

function ShellInner({ nav, current, homeHref, repoUrl, headings = [], asOf, children }: ShellProps) {
  const [opened, { toggle, close }] = useDisclosure(false);
  const navRef = useRef<HTMLDivElement>(null);
  // Etkin bölüm bağlantısı gezinme listesinin görünür alanında değilse yalnız liste kaydırılır (odak ve sayfa
  // kaydırması değişmez); mobil çekmece açılınca da aynı denetim yapılır.
  useEffect(() => {
    const nav = navRef.current;
    const active = nav?.querySelector<HTMLElement>('.nav-link[data-active]');
    if (!nav || !active) return;
    const n = nav.getBoundingClientRect();
    const a = active.getBoundingClientRect();
    if (n.height === 0) return;
    if (a.top < n.top || a.bottom > n.bottom) nav.scrollTop += a.top - n.top - (n.height - a.height) / 2;
  }, [opened]);
  const toc = headings.filter((h) => h.depth === 2);
  const active = useScrollSpy(toc.map((h) => h.slug));

  const { top, groups } = useMemo(() => {
    const topItems: NavItem[] = [];
    const map = new Map<string, NavItem[]>();
    for (const item of nav) {
      if (!item.group) {
        topItems.push(item);
        continue;
      }
      const list = map.get(item.group) ?? [];
      list.push(item);
      map.set(item.group, list);
    }
    return { top: topItems, groups: Array.from(map.entries()) };
  }, [nav]);

  const renderLink = (item: NavItem) => {
    const Icon = sectionIcon(item.icon);
    const isCurrent = item.href === current;
    return (
      <a
        key={item.href}
        href={item.href}
        className="nav-link"
        data-active={isCurrent ? 'true' : undefined}
        aria-current={isCurrent ? 'page' : undefined}
        onClick={close}
      >
        <Icon size={18} stroke={1.75} aria-hidden className="nav-link-icon" />
        <span className="nav-link-label">{item.label}</span>
      </a>
    );
  };

  return (
    <AppShell
      header={{ height: HEADER_HEIGHT }}
      navbar={{ width: NAVBAR_WIDTH, breakpoint: 'md', collapsed: { mobile: !opened } }}
      aside={{ width: ASIDE_WIDTH, breakpoint: 'lg', collapsed: { desktop: toc.length === 0, mobile: true } }}
      padding="md"
    >
      <a className="skip-link" href="#icerik">
        İçeriğe atla
      </a>
      <AppShell.Header className="site-header">
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" className="header-start">
            <Burger
              className="burger"
              opened={opened}
              onClick={toggle}
              hiddenFrom="md"
              size="sm"
              aria-label={opened ? 'Menüyü kapat' : 'Menüyü aç'}
              aria-expanded={opened}
              aria-controls="site-nav"
            />
            <Anchor href={homeHref} underline="never" c="inherit" className="brand">
              <span className="brand-mark" aria-hidden>
                F
              </span>
              <span className="brand-name">frappesetup</span>
            </Anchor>
          </Group>
          <Group gap="xs" wrap="nowrap" className="header-end">
            <Text c="dimmed" size="sm" visibleFrom="sm" className="as-of">
              {asOf}
            </Text>
            <a className="icon-btn" href={repoUrl} aria-label="GitHub deposu" title="GitHub deposu">
              <IconBrandGithub size={20} aria-hidden />
            </a>
            <ColorSchemeToggle />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar id="site-nav" p="sm" aria-label="Bölümler" className="site-nav">
        <AppShell.Section grow className="nav-scroll" ref={navRef}>
          <Stack gap={2}>{top.map(renderLink)}</Stack>
          {groups.map(([group, items]) => (
            <Box key={group} mt="md">
              <Text component="p" className="nav-group">
                {group}
              </Text>
              <Stack gap={2}>{items.map(renderLink)}</Stack>
            </Box>
          ))}
        </AppShell.Section>
        <AppShell.Section pt="sm" className="nav-foot">
          <Text size="sm" c="dimmed">
            Güncelleme {asOf}
          </Text>
          <Text size="sm" c="dimmed">
            Kod MIT · İçerik CC BY 4.0
          </Text>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Box id="icerik" className="page" tabIndex={-1}>
          {children}
        </Box>
        <Box component="footer" className="site-footer">
          <Text size="sm" c="dimmed">
            frappesetup · Frappe Headless SaaS mimari karar çerçevesi · son güncelleme {asOf}
          </Text>
          <Group gap="md" wrap="wrap">
            <Anchor href={repoUrl} size="sm">
              GitHub
            </Anchor>
            <Anchor href={`${repoUrl}/blob/main/LICENSE`} size="sm">
              Kod: MIT
            </Anchor>
            <Anchor href={`${repoUrl}/blob/main/LICENSE-CONTENT`} size="sm">
              İçerik: CC BY 4.0
            </Anchor>
          </Group>
        </Box>
      </AppShell.Main>

      {toc.length > 0 && (
        <AppShell.Aside p="md" component="aside" aria-label="Bu sayfada" className="site-aside">
          <Text component="p" className="nav-group">
            Bu sayfada
          </Text>
          <Stack gap={2} component="ol" className="toc">
            {toc.map((h) => (
              <li key={h.slug}>
                <a href={`#${h.slug}`} className="toc-link" aria-current={active === h.slug ? 'true' : undefined}>
                  {h.text}
                </a>
              </li>
            ))}
          </Stack>
        </AppShell.Aside>
      )}
    </AppShell>
  );
}

export default function Shell(props: ShellProps) {
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto" cssVariablesResolver={cssVariablesResolver}>
      <ShellInner {...props} />
    </MantineProvider>
  );
}

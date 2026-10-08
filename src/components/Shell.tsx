import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  ActionIcon,
  Anchor,
  AppShell,
  Box,
  Burger,
  Group,
  MantineProvider,
  NavLink,
  ScrollArea,
  Stack,
  Text,
  Tooltip,
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
const HEADER_HEIGHT = 60;
const NAVBAR_WIDTH = 280;
const ASIDE_WIDTH = 248;

function ColorSchemeToggle() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = mounted && colorScheme === 'dark';
  const label = dark ? 'Açık temaya geç' : 'Koyu temaya geç';
  return (
    <Tooltip label={label} withArrow>
      <ActionIcon
        variant="subtle"
        size="lg"
        aria-label={label}
        data-testid="color-scheme-toggle"
        onClick={() => setColorScheme(dark ? 'light' : 'dark')}
      >
        {dark ? <IconSun size={20} /> : <IconMoon size={20} />}
      </ActionIcon>
    </Tooltip>
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
      <NavLink
        key={item.href}
        href={item.href}
        label={item.label}
        leftSection={<Icon size={18} stroke={1.75} aria-hidden />}
        active={isCurrent}
        aria-current={isCurrent ? 'page' : undefined}
        onClick={close}
        variant="light"
        className="nav-link"
      />
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
          <Group gap="sm" wrap="nowrap">
            <Burger
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
          <Group gap="xs" wrap="nowrap">
            <Text c="dimmed" size="sm" visibleFrom="sm" className="as-of">
              {asOf}
            </Text>
            <Tooltip label="GitHub deposu" withArrow>
              <ActionIcon
                component="a"
                href={repoUrl}
                variant="subtle"
                size="lg"
                aria-label="GitHub deposu"
              >
                <IconBrandGithub size={20} />
              </ActionIcon>
            </Tooltip>
            <ColorSchemeToggle />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar id="site-nav" p="sm" aria-label="Bölümler" className="site-nav">
        <AppShell.Section grow component={ScrollArea} type="auto" offsetScrollbars>
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

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
import { IconBrandGithub, IconChevronDown, IconMoon, IconSun } from '@tabler/icons-react';
import { cssVariablesResolver, theme } from '../theme';
import { sectionIcon } from './icons';
import { COLLAPSIBLE_GROUPS } from '../data/sections';

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

// Layout constants (px): AppShell turns them into CSS variables; matches --fs-header-h in global.css.
// Shell JS budget (AGENTS.md): only the Mantine components the shell really needs are used; navigation links
// and icon buttons are plain elements drawn in global.css with the same tokens (no Tooltip/ScrollArea/NavLink/ActionIcon).
const HEADER_HEIGHT = 60;
const NAVBAR_WIDTH = 280;
const ASIDE_WIDTH = 248;

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  // An 'auto' preference (nothing saved) resolves to the operating system scheme; the first value is read in the effect and starts the same as the SSR output.
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
      disabled={!mounted}
      data-testid="color-scheme-toggle"
      onClick={() => setColorScheme(dark ? 'light' : 'dark')}
    >
      {dark ? <IconSun size={20} aria-hidden /> : <IconMoon size={20} aria-hidden />}
    </button>
  );
}

// Watches the h2 elements on the page; highlights in the "Bu sayfada" list the last section that has passed the reading line (below the header).
// Scroll-based and deterministic (no cross-browser differences in the first IntersectionObserver callback).
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

// Sidebar collapsible group: a real <button> (focusable and opened with the keyboard) + aria-expanded; no Mantine component.
function CollapsibleGroup({
  id,
  label,
  icon,
  defaultOpened,
  ready,
  children,
}: {
  id: string;
  label: string;
  icon: string;
  defaultOpened: boolean;
  ready: boolean;
  children: ReactNode;
}) {
  const [opened, setOpened] = useState(defaultOpened);
  const GroupIcon = sectionIcon(icon);
  const panelId = `nav-group-${id}`;
  return (
    <>
      <button
        type="button"
        className="nav-link nav-wrapper"
        disabled={!ready}
        aria-expanded={opened}
        aria-controls={panelId}
        data-testid={`nav-wrapper-${id}`}
        onClick={() => setOpened((v) => !v)}
      >
        <GroupIcon size={18} stroke={1.75} aria-hidden className="nav-link-icon" />
        <span className="nav-link-label">{label}</span>
        <IconChevronDown size={18} aria-hidden className="nav-wrapper-chevron" />
      </button>
      <div id={panelId} hidden={!opened} role="group" aria-label={label} className="nav-wrapper-panel">
        <Stack gap={2}>{children}</Stack>
      </div>
    </>
  );
}

function ShellInner({ nav, current, homeHref, repoUrl, headings = [], asOf, children }: ShellProps) {
  const [opened, { toggle, close }] = useDisclosure(false);
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);
  const navRef = useRef<HTMLDivElement>(null);
  // If the active section link is not in the visible area of the navigation list, only the list is scrolled (focus and page
  // scroll do not change); the same check runs when the mobile drawer opens.
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
          <Group gap={0} wrap="nowrap" className="header-start">
            <Burger
              className="burger"
              opened={opened}
              onClick={toggle}
              disabled={!ready}
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
          <Group gap={0} wrap="nowrap" className="header-end">
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
          {groups.map(([group, items]) => {
            const wrapperIcon = COLLAPSIBLE_GROUPS[group];
            if (wrapperIcon) {
              return (
                <Box key={group} mt="md">
                  <CollapsibleGroup
                    id={group.toLowerCase()}
                    label={group}
                    icon={wrapperIcon}
                    defaultOpened={items.some((item) => item.href === current)}
                    ready={ready}
                  >
                    {items.map(renderLink)}
                  </CollapsibleGroup>
                </Box>
              );
            }
            return (
              <Box key={group} mt="md">
                <Text component="p" className="nav-group">
                  {group}
                </Text>
                <Stack gap={2}>{items.map(renderLink)}</Stack>
              </Box>
            );
          })}
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
            <Anchor href={repoUrl} size="sm" className="footer-link">
              GitHub
            </Anchor>
            <Anchor href={`${repoUrl}/blob/main/LICENSE`} size="sm" className="footer-link">
              Kod: MIT
            </Anchor>
            <Anchor href={`${repoUrl}/blob/main/LICENSE-CONTENT`} size="sm" className="footer-link">
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

import { useEffect, useState, type ReactNode } from 'react';
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
  Title,
  Tooltip,
  useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconMoon, IconSun, IconBrandGithub } from '@tabler/icons-react';
import { theme } from '../theme';

export interface NavItem {
  href: string;
  label: string;
  order: number;
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
        onClick={() => setColorScheme(dark ? 'light' : 'dark')}
      >
        {dark ? <IconSun size={20} /> : <IconMoon size={20} />}
      </ActionIcon>
    </Tooltip>
  );
}

function ShellInner({ nav, current, homeHref, repoUrl, headings = [], asOf, children }: ShellProps) {
  const [opened, { toggle, close }] = useDisclosure(false);
  const toc = headings.filter((h) => h.depth === 2);

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 272, breakpoint: 'md', collapsed: { mobile: !opened } }}
      aside={{ width: 240, breakpoint: 'lg', collapsed: { desktop: toc.length === 0, mobile: true } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="md"
              size="sm"
              aria-label={opened ? 'Menüyü kapat' : 'Menüyü aç'}
            />
            <Anchor href={homeHref} underline="never" c="inherit">
              <Group gap={8} wrap="nowrap">
                <Box
                  aria-hidden
                  style={{
                    width: 26,
                    height: 26,
                    borderRadius: 7,
                    background: 'var(--fs-accent)',
                    display: 'grid',
                    placeItems: 'center',
                    color: 'white',
                    fontWeight: 800,
                    fontSize: '1rem',
                  }}
                >
                  F
                </Box>
                <Text fw={650} size="lg" style={{ letterSpacing: '-0.01em' }}>
                  frappesetup
                </Text>
              </Group>
            </Anchor>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Text c="dimmed" size="sm" visibleFrom="sm">
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

      <AppShell.Navbar p="sm" component="nav" aria-label="Bölümler">
        <AppShell.Section grow component={ScrollArea}>
          <Stack gap={2}>
            {nav.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                label={item.label}
                active={item.href === current}
                onClick={close}
                variant="light"
                style={{ borderRadius: 'var(--mantine-radius-sm)' }}
              />
            ))}
          </Stack>
        </AppShell.Section>
        <AppShell.Section pt="sm">
          <Text size="sm" c="dimmed">
            Frappe Headless SaaS — mimari karar çerçevesi
          </Text>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Box style={{ maxWidth: 'min(100%, 80rem)', margin: '0 auto' }}>{children}</Box>
      </AppShell.Main>

      {toc.length > 0 && (
        <AppShell.Aside p="md" component="aside" aria-label="Bu sayfada">
          <Title order={2} size="1rem" c="dimmed" mb="sm" tt="uppercase" style={{ letterSpacing: '0.04em' }}>
            Bu sayfada
          </Title>
          <Stack gap={4}>
            {toc.map((h) => (
              <Anchor key={h.slug} href={`#${h.slug}`} size="sm" c="inherit" underline="hover">
                {h.text}
              </Anchor>
            ))}
          </Stack>
        </AppShell.Aside>
      )}
    </AppShell>
  );
}

export default function Shell(props: ShellProps) {
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <ShellInner {...props} />
    </MantineProvider>
  );
}

import { useMemo, useState, type ReactNode } from 'react';
import {
  Badge,
  Box,
  Button,
  Group,
  MantineProvider,
  Select,
  Switch,
  Table,
  Text,
  TextInput,
} from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { theme } from '../theme';

export interface Requirement {
  id: string;
  title: string;
  detail: string;
  rail: string;
  priority: 'MUST' | 'SHOULD' | 'MAY' | string;
  phase: string;
  source: string;
  owner?: string;
}

interface Props {
  items: Requirement[];
}

const PRIORITY_COLOR: Record<string, string> = { MUST: 'sea', SHOULD: 'amber', MAY: 'gray' };

const RAIL_ORDER = [
  'R1 Press',
  'R2 Frappe yapılandırma',
  'R2 Frappe geliştirme',
  'R3 Frontend',
  'R4 Keycloak',
  'R5 AI',
  'Shell',
  'App çerçevesi',
  'Çapraz',
  'R6 Operasyon düzlemi',
];

function idKey(id: string): [number, number] {
  const [prefix, n] = id.split('-');
  return [prefix === 'G' ? 0 : prefix === 'SA' ? 1 : 2, Number(n) || 0];
}

function byId(a: Requirement, b: Requirement) {
  const [pa, na] = idKey(a.id);
  const [pb, nb] = idKey(b.id);
  return pa - pb || na - nb;
}

// `kod` parçalarını <code> olarak gösterir; başka markdown işlenmez.
function inlineCode(text: string): ReactNode[] {
  return text.split('`').map((part, i) =>
    i % 2 === 1 ? (
      <code key={i} className="req-code">
        {part}
      </code>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

function options(values: string[], order?: string[]) {
  const uniq = Array.from(new Set(values));
  if (order) uniq.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  else uniq.sort((a, b) => a.localeCompare(b, 'tr'));
  return uniq.map((v) => ({ value: v, label: v }));
}

function Explorer({ items }: Props) {
  const [q, setQ] = useState('');
  const [priority, setPriority] = useState<string | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [rail, setRail] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [showDetail, setShowDetail] = useState(true);

  const sorted = useMemo(() => [...items].sort(byId), [items]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLocaleLowerCase('tr');
    return sorted.filter((r) => {
      if (priority && r.priority !== priority) return false;
      if (phase && r.phase !== phase) return false;
      if (rail && r.rail !== rail) return false;
      if (source && r.source !== source) return false;
      if (!needle) return true;
      const hay = `${r.id} ${r.title} ${r.detail} ${r.owner ?? ''}`.toLocaleLowerCase('tr');
      return hay.includes(needle);
    });
  }, [sorted, q, priority, phase, rail, source]);

  const active = Boolean(q || priority || phase || rail || source);
  const reset = () => {
    setQ('');
    setPriority(null);
    setPhase(null);
    setRail(null);
    setSource(null);
  };

  return (
    <Box component="section" aria-labelledby="req-explorer-title" className="req-explorer">
      <Text component="h2" id="req-explorer-title" fw={650} size="xl" mb="xs">
        Gereksinim gezgini
      </Text>
      <Text c="dimmed" mb="md">
        {items.length} gereksinimi ray, öncelik, faz ve kaynağa göre süz; metin araması başlık, ayrıntı ve
        sahip alanlarında çalışır. Tam gerekçeler aşağıdaki tablolarda ve ilgili ray bölümlerindedir.
      </Text>

      <Group gap="sm" align="flex-end" wrap="wrap" mb="sm">
        <TextInput
          label="Ara"
          placeholder="örn. iyzico, Keycloak, G-45"
          value={q}
          onChange={(e) => setQ(e.currentTarget.value)}
          leftSection={<IconSearch size={18} aria-hidden />}
          style={{ flex: '1 1 16rem', minWidth: '12rem' }}
        />
        <Select
          label="Öncelik"
          placeholder="Hepsi"
          data={options(items.map((r) => r.priority), ['MUST', 'SHOULD', 'MAY'])}
          value={priority}
          onChange={setPriority}
          clearable
          style={{ flex: '1 1 9rem' }}
        />
        <Select
          label="Faz"
          placeholder="Hepsi"
          data={options(items.map((r) => r.phase))}
          value={phase}
          onChange={setPhase}
          clearable
          style={{ flex: '1 1 8rem' }}
        />
        <Select
          label="Ray"
          placeholder="Hepsi"
          data={options(items.map((r) => r.rail), RAIL_ORDER)}
          value={rail}
          onChange={setRail}
          clearable
          style={{ flex: '1 1 14rem' }}
        />
        <Select
          label="Kaynak"
          placeholder="Hepsi"
          data={options(items.map((r) => r.source), ['native', 'configure', 'develop', 'integrate'])}
          value={source}
          onChange={setSource}
          clearable
          style={{ flex: '1 1 9rem' }}
        />
      </Group>

      <Group justify="space-between" mb="md" wrap="wrap" gap="sm">
        <Group gap="md" wrap="wrap">
          <Text role="status" aria-live="polite" data-testid="req-count">
            <strong>{filtered.length}</strong> / {items.length} gereksinim
          </Text>
          <Switch
            label="Ayrıntıları göster"
            checked={showDetail}
            onChange={(e) => setShowDetail(e.currentTarget.checked)}
          />
        </Group>
        {active && (
          <Button variant="subtle" onClick={reset}>
            Filtreleri temizle
          </Button>
        )}
      </Group>

      <Table.ScrollContainer minWidth={showDetail ? 1040 : 820} type="native">
        <Table stickyHeader highlightOnHover withRowBorders data-testid="req-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ minWidth: '5.5rem' }}>ID</Table.Th>
              <Table.Th style={{ minWidth: showDetail ? '30rem' : '18rem' }}>Gereksinim</Table.Th>
              <Table.Th style={{ minWidth: '11rem' }}>Ray</Table.Th>
              <Table.Th style={{ minWidth: '7rem' }}>Öncelik</Table.Th>
              <Table.Th style={{ minWidth: '5rem' }}>Faz</Table.Th>
              <Table.Th style={{ minWidth: '7rem' }}>Kaynak</Table.Th>
              <Table.Th style={{ minWidth: '12rem' }}>Sahip</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filtered.map((r) => (
              <Table.Tr key={r.id}>
                <Table.Td>
                  <Text component="span" ff="monospace" fw={600} id={`req-${r.id}`}>
                    {r.id}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text fw={600}>{r.title}</Text>
                  {showDetail && (
                    <Text c="dimmed" mt={4} style={{ maxWidth: '60ch' }}>
                      {inlineCode(r.detail)}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>{r.rail}</Table.Td>
                <Table.Td>
                  <Badge color={PRIORITY_COLOR[r.priority] ?? 'gray'}>{r.priority}</Badge>
                </Table.Td>
                <Table.Td>{r.phase}</Table.Td>
                <Table.Td>{r.source}</Table.Td>
                <Table.Td>{r.owner ?? '—'}</Table.Td>
              </Table.Tr>
            ))}
            {filtered.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={7}>
                  <Text c="dimmed">Bu filtrelerle eşleşen gereksinim yok.</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Box>
  );
}

export default function RequirementsExplorer(props: Props) {
  return (
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Explorer {...props} />
    </MantineProvider>
  );
}

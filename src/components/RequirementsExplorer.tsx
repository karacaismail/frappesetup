import { Fragment, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  Badge,
  Box,
  Button,
  Group,
  MantineProvider,
  Switch,
  Table,
  Text,
  TextInput,
  type MantineColorScheme,
} from '@mantine/core';
import { IconFilterOff, IconSearch } from '@tabler/icons-react';
import { theme } from '../theme';

export interface Requirement {
  id: string;
  title: string;
  detail: string;
  rail: string;
  priority: string;
  phase: string;
  source: string;
  owner?: string;
}

interface Props {
  items: Requirement[];
}

const PRIORITIES = ['MUST', 'SHOULD', 'MAY'];
// Dolgulu rozet/düğme renkleri: sea-8 üzerinde beyaz 5.1:1, amber-7 üzerinde koyu metin (autoContrast),
// gray-7 üzerinde beyaz 7:1.
// Açık tonlar şemaya göre değişmez (bileşen düzeyi autoContrast şemayı bilmez): sea-8 üzerinde beyaz 5.1:1.
const PRIORITY_COLOR: Record<string, string> = { MUST: 'sea.8', SHOULD: 'amber.7', MAY: 'gray.7' };
const PRIORITY_HINT: Record<string, string> = {
  MUST: 'sabit kararların veya mevzuatın doğrudan sonucu',
  SHOULD: 'bağlamsal öneri',
  MAY: 'isteğe bağlı',
};

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

// `kod` parçalarını <code> olarak gösterir; başka markdown işlenmez. Kod dışı parçalar sarmalayıcısız düz metindir
// (Gereksinimler HTML bütçesi; görünüm aynı).
function inlineCode(text: string): ReactNode[] {
  return text.split('`').map((part, i) =>
    i % 2 === 1 ? (
      <code key={i} className="req-code">
        {part}
      </code>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

function options(values: string[], order?: string[]) {
  const uniq = Array.from(new Set(values));
  if (order) uniq.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  else uniq.sort((a, b) => a.localeCompare(b, 'tr'));
  return uniq;
}

function countBy(items: Requirement[], key: 'priority' | 'phase' | 'rail' | 'source') {
  const m = new Map<string, number>();
  for (const r of items) m.set(r[key], (m.get(r[key]) ?? 0) + 1);
  return m;
}

// Tek seçimli süzgeç: açılır liste yerine aria-pressed düğme grubu (kabuk/ada JS bütçesi; açılır panel kodu yok).
function ToggleGroup(props: {
  label: string;
  values: string[];
  counts: Map<string, number>;
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  const id = useId();
  return (
    <div className="req-toggle-group">
      <Text component="span" id={id} fw={600} className="req-toggle-label">
        {props.label}
      </Text>
      <Group gap="xs" wrap="wrap" role="group" aria-labelledby={id}>
        {props.values.map((v) => (
          <Button
            key={v}
            size="compact-md"
            radius="xl"
            variant={props.value === v ? 'filled' : 'default'}
            aria-pressed={props.value === v}
            onClick={() => props.onChange(props.value === v ? null : v)}
          >
            {v} · {props.counts.get(v) ?? 0}
          </Button>
        ))}
      </Group>
    </div>
  );
}

function Explorer({ items }: Props) {
  const [q, setQ] = useState('');
  const [priority, setPriority] = useState<string | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [rail, setRail] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [showDetail, setShowDetail] = useState(true);
  const searchRef = useRef<HTMLInputElement>(null);
  const detailRef = useRef<HTMLInputElement>(null);

  // Ada JS'i inmeden önce sunucu HTML'ine yazılan metin DOM'da kalır, ama React durumu boş başlar:
  // React 19 hidrasyonda DOM değerini korur, değer izleyicisini bu değerle başlatır ve değişikliği
  // onChange olarak yeniden oynatmaz. Bağlanınca erken girdiyi (arama metni, ayrıntı anahtarı) duruma al.
  useEffect(() => {
    if (searchRef.current) setQ(searchRef.current.value);
    if (detailRef.current) setShowDetail(detailRef.current.checked);
  }, []);

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

  const priorityCounts = useMemo(() => countBy(items, 'priority'), [items]);
  const phaseCounts = useMemo(() => countBy(items, 'phase'), [items]);
  const railCounts = useMemo(() => countBy(items, 'rail'), [items]);
  const sourceCounts = useMemo(() => countBy(items, 'source'), [items]);
  const facetCount = [phase, rail, source].filter(Boolean).length;

  const active = Boolean(q || priority || phase || rail || source);
  const reset = () => {
    setQ('');
    setPriority(null);
    setPhase(null);
    setRail(null);
    setSource(null);
  };

  const meta = (r: Requirement) => (
    <>
      <span>{r.rail}</span>
      <span aria-hidden>·</span>
      <span>{r.phase}</span>
      <span aria-hidden>·</span>
      <span>{r.source}</span>
      {r.owner && (
        <>
          <span aria-hidden>·</span>
          <span>{r.owner}</span>
        </>
      )}
    </>
  );

  return (
    <Box component="section" aria-labelledby="req-explorer-title" className="req-explorer">
      <div className="req-head">
        <div>
          <Text component="h2" id="req-explorer-title" fw={650} size="xl" mb={4}>
            Gereksinim gezgini
          </Text>
          <Text c="dimmed">
            {items.length} gereksinimi ray, öncelik, faz ve kaynağa göre süz; arama başlık, ayrıntı ve sahip
            alanlarında çalışır.
          </Text>
        </div>
        <Group gap="xs" wrap="wrap" role="group" aria-label="Önceliğe göre süz">
          {PRIORITIES.map((p) => (
            <Button
              key={p}
              size="compact-md"
              radius="xl"
              color={PRIORITY_COLOR[p]}
              variant={priority === p ? 'filled' : 'default'}
              aria-pressed={priority === p}
              title={PRIORITY_HINT[p]}
              onClick={() => setPriority(priority === p ? null : p)}
            >
              {p} · {priorityCounts.get(p) ?? 0}
            </Button>
          ))}
        </Group>
      </div>

      <div className="req-filters">
        <TextInput
          ref={searchRef}
          label="Ara"
          placeholder="örn. iyzico, Keycloak, G-45"
          value={q}
          onChange={(e) => setQ(e.currentTarget.value)}
          leftSection={<IconSearch size={18} aria-hidden />}
        />
      </div>

      <details className="req-more">
        <summary>
          Faz, ray ve kaynak süzgeçleri{facetCount > 0 ? ` · ${facetCount} etkin` : ''}
        </summary>
        <div className="req-more-body">
          <ToggleGroup
            label="Faz"
            values={options(items.map((r) => r.phase))}
            counts={phaseCounts}
            value={phase}
            onChange={setPhase}
          />
          <ToggleGroup
            label="Ray"
            values={options(items.map((r) => r.rail), RAIL_ORDER)}
            counts={railCounts}
            value={rail}
            onChange={setRail}
          />
          <ToggleGroup
            label="Kaynak"
            values={options(items.map((r) => r.source), ['native', 'configure', 'develop', 'integrate'])}
            counts={sourceCounts}
            value={source}
            onChange={setSource}
          />
        </div>
      </details>

      <div className="req-bar">
        <Group gap="md" wrap="wrap">
          <Text role="status" aria-live="polite" data-testid="req-count">
            <strong>{filtered.length}</strong> / {items.length} gereksinim
          </Text>
          <Switch
            ref={detailRef}
            label="Ayrıntıları göster"
            checked={showDetail}
            onChange={(e) => setShowDetail(e.currentTarget.checked)}
          />
        </Group>
        {active && (
          <Button variant="subtle" leftSection={<IconFilterOff size={18} aria-hidden />} onClick={reset}>
            Filtreleri temizle
          </Button>
        )}
      </div>

      {/* Dar ekran: kart listesi */}
      <Box hiddenFrom="sm" component="ul" className="req-cards" aria-label="Gereksinimler (kart görünümü)">
        {filtered.map((r) => (
          <li key={r.id} className="req-card" id={`req-${r.id}`}>
            <div className="req-card-top">
              <code className="req-id">{r.id}</code>
              <Badge color={PRIORITY_COLOR[r.priority] ?? 'gray.7'}>{r.priority}</Badge>
            </div>
            {/* Liste satırlarında Mantine Text yerine sade <p>: aynı görünüm global.css'teki sınıf kurallarından. */}
            <p className="req-card-title">{r.title}</p>
            {showDetail && <p className="req-card-detail">{inlineCode(r.detail)}</p>}
            <div className="req-meta">{meta(r)}</div>
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="req-card">
            <Text c="dimmed">Bu filtrelerle eşleşen gereksinim yok.</Text>
          </li>
        )}
      </Box>

      {/* Geniş ekran: tablo, kendi kapsayıcısında yatay kayar */}
      <Box visibleFrom="sm">
        <Table.ScrollContainer
          minWidth={showDetail ? 936 : 808}
          type="native"
          tabIndex={0}
          role="region"
          aria-label="Gereksinim tablosu (yatay kaydırılabilir)"
        >
          <Table highlightOnHover withRowBorders data-testid="req-table" className="req-table">
            <Table.Thead>
              <Table.Tr>
                <Table.Th style={{ minWidth: '5.5rem' }}>ID</Table.Th>
                <Table.Th style={{ minWidth: showDetail ? '24rem' : '16rem' }}>Gereksinim</Table.Th>
                <Table.Th style={{ minWidth: '10rem' }}>Ray</Table.Th>
                <Table.Th style={{ minWidth: '7rem' }}>Öncelik</Table.Th>
                <Table.Th style={{ minWidth: '5rem' }}>Faz</Table.Th>
                <Table.Th style={{ minWidth: '7rem' }}>Kaynak</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filtered.map((r) => (
                <Table.Tr key={r.id}>
                  <Table.Td>
                    <code className="req-id">{r.id}</code>
                  </Table.Td>
                  <Table.Td>
                    <p className="req-title">{r.title}</p>
                    {showDetail && <p className="req-detail">{inlineCode(r.detail)}</p>}
                    {/* Sahip ayrı sütun değil, kart görünümündeki gibi gereksinim hücresindedir; içerik sığmazsa tablo kendi kapsayıcısında kayar. */}
                    {r.owner && <p className="req-owner">Sahip: {r.owner}</p>}
                  </Table.Td>
                  <Table.Td>{r.rail}</Table.Td>
                  <Table.Td>
                    <Badge color={PRIORITY_COLOR[r.priority] ?? 'gray.7'}>{r.priority}</Badge>
                  </Table.Td>
                  <Table.Td>{r.phase}</Table.Td>
                  <Table.Td>{r.source}</Table.Td>
                </Table.Tr>
              ))}
              {filtered.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={6}>
                    <Text c="dimmed">Bu filtrelerle eşleşen gereksinim yok.</Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Box>
    </Box>
  );
}

// Kabuk (Shell) renk şemasını yönetir; bu ada html özniteliğini izleyip aynı şemayı zorlar.
// Böylece iki MantineProvider arasında şema sapması olmaz; CSS değişkenleri kabuktan gelir.
function useDocumentColorScheme(): MantineColorScheme | undefined {
  const [scheme, setScheme] = useState<MantineColorScheme | undefined>(undefined);
  useEffect(() => {
    const read = () => {
      const v = document.documentElement.getAttribute('data-mantine-color-scheme');
      setScheme(v === 'dark' || v === 'light' ? v : undefined);
    };
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-mantine-color-scheme'] });
    return () => mo.disconnect();
  }, []);
  return scheme;
}

export default function RequirementsExplorer(props: Props) {
  const scheme = useDocumentColorScheme();
  return (
    <MantineProvider
      theme={theme}
      defaultColorScheme="auto"
      forceColorScheme={scheme === 'dark' || scheme === 'light' ? scheme : undefined}
      withCssVariables={false}
      withGlobalClasses={false}
    >
      <Explorer {...props} />
    </MantineProvider>
  );
}

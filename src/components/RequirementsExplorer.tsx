import { Fragment, startTransition, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
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
  useMantineTheme,
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

// Görev panosu verisi (src/data/task-board.json). Gereksinim kaydı değişmez; durum, düzey ve epic ayrı dosyadadır.
export interface TaskBoard {
  epics: { id: string; title: string }[];
  statuses: { id: string; label: string }[];
  levels: { id: string; label: string }[];
  items: Record<string, { epic: string; status: string; level: string; evidence?: { commit: string; tests: string[] } }>;
}

interface Task extends Requirement {
  epic: string;
  status: string;
  level: string;
  evidence?: string;
}

type RequirementRow = [
  id: string, title: string, detail: string, rail: string,
  priority: string, phase: string, source: string, owner: string | null | undefined,
  epic: number, status: number, level: number, evidence?: string,
];

// Adaya giden sözlük: epic, durum, düzey ve faz adları bir kez gönderilir; satırlar yalnız sıra numarası taşır.
export interface BoardMeta {
  epics: [id: string, title: string][];
  statuses: [id: string, label: string][];
  levels: [id: string, label: string][];
  phases: [id: string, title: string][];
}

export function toBoardMeta(board: TaskBoard, phases: { id: string; title: string }[]): BoardMeta {
  return {
    epics: board.epics.map((e) => [e.id, e.title]),
    statuses: board.statuses.map((s) => [s.id, s.label]),
    levels: board.levels.map((l) => [l.id, l.label]),
    phases: phases.map((p) => [p.id, p.title]),
  };
}

const fileName = (path: string) => path.slice(path.lastIndexOf('/') + 1);

// Ada verisinde her gereksinim için alan adlarını yinelemeyin.
export function toRequirementRow(
  { id, title, detail, rail, priority, phase, source, owner }: Requirement,
  board: TaskBoard,
): RequirementRow {
  const it = board.items[id];
  const row: RequirementRow = [
    id, title, detail, rail, priority, phase, source, owner,
    board.epics.findIndex((e) => e.id === it.epic),
    board.statuses.findIndex((s) => s.id === it.status),
    board.levels.findIndex((l) => l.id === it.level),
  ];
  if (it.evidence) row.push(`${it.evidence.commit} commit'i. Test: ${it.evidence.tests.map(fileName).join(', ')}.`);
  return row;
}

let decodedRows: { source: string; items: Task[] } | undefined;

function decodeRequirements(source: string, meta: BoardMeta) {
  if (decodedRows?.source === source) return decodedRows.items;
  const rows: RequirementRow[] = JSON.parse(source);
  const items = rows.map(([id, title, detail, rail, priority, phase, source, owner, epic, status, level, evidence]) => ({
    id, title, detail, rail, priority, phase, source, owner: owner ?? undefined,
    epic: meta.epics[epic][0], status: meta.statuses[status][0], level: meta.levels[level][0], evidence,
  }));
  decodedRows = { source, items };
  return items;
}

interface Props {
  items: Task[];
  meta: BoardMeta;
}

const PRIORITIES = ['MUST', 'SHOULD', 'MAY'];
// Dolgulu rozet/düğme renkleri: sea-8 üzerinde beyaz 5.1:1, amber-7 üzerinde koyu metin (autoContrast),
// gray-7 üzerinde beyaz 7:1.
// Açık tonlar şemaya göre değişmez (bileşen düzeyi autoContrast şemayı bilmez): sea-8 üzerinde beyaz 5.1:1.
const PRIORITY_COLOR: Record<string, string> = { MUST: 'sea.8', SHOULD: 'amber.7', MAY: 'gray.7' };
// Seçili süzgeç ve görünüm düğmesinin dolgusu: koyu temada da sea-8 üzerinde beyaz metin 5.1:1.
const FILL = 'sea.8';
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
      <code key={i} className={/\s/.test(part) ? 'req-code-wrap' : undefined}>
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

type FacetKey = 'priority' | 'phase' | 'rail' | 'source' | 'epic' | 'status' | 'level';

function countBy(items: Task[], key: FacetKey) {
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
  labelOf?: (v: string) => string;
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
            color={FILL}
            variant={props.value === v ? 'filled' : 'default'}
            aria-pressed={props.value === v}
            onClick={() => props.onChange(props.value === v ? null : v)}
          >
            {props.labelOf ? props.labelOf(v) : v} · {props.counts.get(v) ?? 0}
          </Button>
        ))}
      </Group>
    </div>
  );
}

const DONE = 'done';

function doneCount(items: Task[]) {
  return items.reduce((n, r) => n + (r.status === DONE ? 1 : 0), 0);
}

// Durum etiketi görünür metindir (ekran okuyucu da okur); simge yalnız süstür ve CSS'tedir.
function StatusLabel({ status, label }: { status: string; label: string }) {
  return (
    <span className="task-status" data-status={status}>
      {label}
    </span>
  );
}

function Explorer({ items, meta: board }: Props) {
  const [q, setQ] = useState('');
  const [priority, setPriority] = useState<string | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [rail, setRail] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [epic, setEpic] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [level, setLevel] = useState<string | null>(null);
  const [view, setView] = useState<'table' | 'grouped'>('table');
  const [showDetail, setShowDetail] = useState(true);
  const [hasTable, setHasTable] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const detailRef = useRef<HTMLInputElement>(null);
  const cardsRef = useRef<HTMLUListElement>(null);
  const tableRef = useRef<HTMLDivElement>(null);
  const { sm } = useMantineTheme().breakpoints;

  // Ada JS'i inmeden önce sunucu HTML'ine yazılan metin DOM'da kalır, ama React durumu boş başlar:
  // React 19 hidrasyonda DOM değerini korur, değer izleyicisini bu değerle başlatır ve değişikliği
  // onChange olarak yeniden oynatmaz. Bağlanınca erken girdiyi (arama metni, ayrıntı anahtarı) duruma al.
  useEffect(() => {
    if (searchRef.current) setQ(searchRef.current.value);
    if (detailRef.current) setShowDetail(detailRef.current.checked);
  }, []);

  useEffect(() => {
    const desktop = window.matchMedia(`(min-width: ${sm})`);
    const cards = view === 'table' ? cardsRef.current : null;
    let cancelPending: (() => void) | undefined;
    let switching = false;
    let disposed = false;
    const canShowTable = () => desktop.matches && cards &&
      !cards.contains(document.activeElement) && cards.getBoundingClientRect().top >= 0;

    const updateLayout = () => {
      if (disposed) return;
      if (!desktop.matches) {
        cancelPending?.();
        cancelPending = undefined;
        if (tableRef.current?.contains(document.activeElement)) {
          searchRef.current?.focus({ preventScroll: true });
        }
        if (hasTable || switching) setHasTable(false);
        switching = false;
        return;
      }
      if (hasTable) return;
      if (!canShowTable()) {
        if (switching) {
          switching = false;
          setHasTable(false);
        }
        return;
      }
      if (cancelPending || switching) return;

      const showTable = () => {
        cancelPending = undefined;
        if (!canShowTable()) return;
        switching = true;
        startTransition(() => setHasTable(true));
      };
      if (typeof window.requestIdleCallback === 'function') {
        const id = window.requestIdleCallback(showTable, { timeout: 1500 });
        cancelPending = () => window.cancelIdleCallback(id);
      } else {
        const id = window.setTimeout(showTable, 32);
        cancelPending = () => window.clearTimeout(id);
      }
    };

    updateLayout();
    desktop.addEventListener('change', updateLayout);
    if (cards) window.addEventListener('scroll', updateLayout, { passive: true });
    const handleBlur = () => {
      queueMicrotask(updateLayout);
    };
    cards?.addEventListener('focusin', updateLayout);
    cards?.addEventListener('focusout', handleBlur);
    return () => {
      disposed = true;
      cancelPending?.();
      desktop.removeEventListener('change', updateLayout);
      window.removeEventListener('scroll', updateLayout);
      cards?.removeEventListener('focusin', updateLayout);
      cards?.removeEventListener('focusout', handleBlur);
    };
  }, [hasTable, sm, view]);

  const sorted = useMemo(() => [...items].sort(byId), [items]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLocaleLowerCase('tr');
    return sorted.filter((r) => {
      if (priority && r.priority !== priority) return false;
      if (phase && r.phase !== phase) return false;
      if (rail && r.rail !== rail) return false;
      if (source && r.source !== source) return false;
      if (epic && r.epic !== epic) return false;
      if (status && r.status !== status) return false;
      if (level && r.level !== level) return false;
      if (!needle) return true;
      const hay = `${r.id} ${r.title} ${r.detail.replaceAll('`', '')} ${r.owner ?? ''}`.toLocaleLowerCase('tr');
      return hay.includes(needle);
    });
  }, [sorted, q, priority, phase, rail, source, epic, status, level]);

  const priorityCounts = useMemo(() => countBy(items, 'priority'), [items]);
  const phaseCounts = useMemo(() => countBy(items, 'phase'), [items]);
  const railCounts = useMemo(() => countBy(items, 'rail'), [items]);
  const sourceCounts = useMemo(() => countBy(items, 'source'), [items]);
  const epicCounts = useMemo(() => countBy(items, 'epic'), [items]);
  const statusCounts = useMemo(() => countBy(items, 'status'), [items]);
  const levelCounts = useMemo(() => countBy(items, 'level'), [items]);
  const facetCount = [phase, rail, source, epic, status, level].filter(Boolean).length;

  const nameMap = (pairs: [string, string][]) => new Map(pairs);
  const epicName = useMemo(() => nameMap(board.epics), [board]);
  const statusName = useMemo(() => nameMap(board.statuses), [board]);
  const levelName = useMemo(() => nameMap(board.levels), [board]);
  const phaseName = useMemo(() => nameMap(board.phases), [board]);

  const active = Boolean(q || priority || phase || rail || source || epic || status || level);
  const reset = () => {
    setQ('');
    setPriority(null);
    setPhase(null);
    setRail(null);
    setSource(null);
    setEpic(null);
    setStatus(null);
    setLevel(null);
  };

  // Gruplu görünüm: önce faz, sonra epic (task-board.json sırası). Boş grup gösterilmez.
  const groups = useMemo(() => {
    if (view !== 'grouped') return [];
    return board.phases
      .map(([id, title]) => {
        const inPhase = filtered.filter((r) => r.phase === id);
        const epics = board.epics
          .map(([eid, etitle]) => ({ id: eid, title: etitle, items: inPhase.filter((r) => r.epic === eid) }))
          .filter((e) => e.items.length > 0);
        return { id, title, items: inPhase, epics };
      })
      .filter((g) => g.items.length > 0);
  }, [view, filtered, board]);

  const meta = (r: Task) => (
    <>
      <span>{r.rail}</span>
      <span aria-hidden>·</span>
      <span>{r.phase}</span>
      <span aria-hidden>·</span>
      <span>Düzey: {levelName.get(r.level)}</span>
      <span aria-hidden>·</span>
      <span>Epic: {epicName.get(r.epic)}</span>
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

  const evidence = (r: Task, className: string) =>
    r.evidence && <p className={className}>Kanıt: {r.evidence}</p>;

  const card = (r: Task) => (
    <li key={r.id} className="req-card" id={`req-${r.id}`}>
      <div className="req-card-top">
        <span className="task-card-id">
          <code className="req-id">{r.id}</code>
          <StatusLabel status={r.status} label={statusName.get(r.status) ?? r.status} />
        </span>
        <Badge color={PRIORITY_COLOR[r.priority] ?? 'gray.7'}>{r.priority}</Badge>
      </div>
      {/* Liste satırlarında Mantine Text yerine sade <p>: aynı görünüm global.css'teki sınıf kurallarından. */}
      <p className={r.status === DONE ? 'req-card-title is-done' : 'req-card-title'}>{r.title}</p>
      {showDetail && <p className="req-card-detail">{inlineCode(r.detail)}</p>}
      <div className="req-meta">{meta(r)}</div>
      {evidence(r, 'task-evidence')}
    </li>
  );

  return (
    <Box component="section" aria-labelledby="req-explorer-title" className="req-explorer">
      <div className="req-head">
        <div>
          <Text component="h2" id="req-explorer-title" fw={650} size="xl" mb={4}>
            Görev panosu
          </Text>
          <Text c="dimmed">
            Her gereksinim bir görevdir. {items.length} görevi faz, olgunluk düzeyi, epic, ray, durum ve önceliğe
            göre süzebilirsiniz. Arama başlıkta, ayrıntıda ve sahipte çalışır.
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
          Faz, düzey, epic, durum, ray ve kaynak süzgeçleri{facetCount > 0 ? ` · ${facetCount} etkin` : ''}
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
            label="Olgunluk düzeyi"
            values={options(items.map((r) => r.level), board.levels.map(([id]) => id))}
            counts={levelCounts}
            value={level}
            onChange={setLevel}
            labelOf={(v) => levelName.get(v) ?? v}
          />
          <ToggleGroup
            label="Durum"
            values={options(items.map((r) => r.status), board.statuses.map(([id]) => id))}
            counts={statusCounts}
            value={status}
            onChange={setStatus}
            labelOf={(v) => statusName.get(v) ?? v}
          />
          <ToggleGroup
            label="Epic"
            values={options(items.map((r) => r.epic), board.epics.map(([id]) => id))}
            counts={epicCounts}
            value={epic}
            onChange={setEpic}
            labelOf={(v) => epicName.get(v) ?? v}
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
          <Group gap="xs" wrap="wrap" role="group" aria-label="Görünüm">
            {(
              [
                ['table', 'Tablo'],
                ['grouped', 'Gruplu'],
              ] as const
            ).map(([v, label]) => (
              <Button
                key={v}
                size="compact-md"
                radius="xl"
                color={FILL}
                variant={view === v ? 'filled' : 'default'}
                aria-pressed={view === v}
                onClick={() => setView(v)}
              >
                {label}
              </Button>
            ))}
          </Group>
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

      {view === 'grouped' && (
        <div className="task-groups">
          {groups.map((g) => (
            <div key={g.id} className="task-phase">
              <h3 className="task-phase-title">
                <span>{phaseName.get(g.id) ?? g.id}</span>{' '}
                <span className="task-count">
                  {doneCount(g.items)} / {g.items.length} bitti
                </span>
              </h3>
              {g.epics.map((e) => (
                <div key={e.id} className="task-epic">
                  <h4 className="task-epic-title">
                    <span>{e.title}</span>{' '}
                    <span className="task-count">
                      {doneCount(e.items)} / {e.items.length} bitti
                    </span>
                  </h4>
                  <ul className="task-list">{e.items.map(card)}</ul>
                </div>
              ))}
            </div>
          ))}
          {groups.length === 0 && <Text c="dimmed">Bu filtrelerle eşleşen görev yok.</Text>}
        </div>
      )}

      {/* Sunucu önce kartları gönderir. Tablo tarayıcıda hazırlanır. */}
      {view === 'table' && !hasTable && (
        <Box
          ref={cardsRef}
          component="ul"
          className="req-cards"
          aria-label="Gereksinimler (kart görünümü)"
        >
          {filtered.map(card)}
          {filtered.length === 0 && (
            <li className="req-card">
              <Text c="dimmed">Bu filtrelerle eşleşen gereksinim yok.</Text>
            </li>
          )}
        </Box>
      )}

      {/* Geniş ekran: tablo, kendi kapsayıcısında yatay kayar */}
      {view === 'table' && hasTable && (
        <Box ref={tableRef}>
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
                  <Table.Th style={{ minWidth: showDetail ? '24rem' : '16rem' }}>Görev ve durum</Table.Th>
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
                      {/* Durum, düzey ve epic ayrı sütun değildir: altı sütun 1280 px'te kapsayıcıya sığar. */}
                      <p className="task-row-status">
                        <StatusLabel status={r.status} label={statusName.get(r.status) ?? r.status} />
                      </p>
                      <p className={r.status === DONE ? 'req-title is-done' : 'req-title'}>{r.title}</p>
                      {showDetail && <p className="req-detail">{inlineCode(r.detail)}</p>}
                      {/* Sahip ayrı sütun değil, kart görünümündeki gibi gereksinim hücresindedir; içerik sığmazsa tablo kendi kapsayıcısında kayar. */}
                      {r.owner && <p className="req-owner">Sahip: {r.owner}</p>}
                      <p className="req-owner">
                        Epic: {epicName.get(r.epic)} · Düzey: {levelName.get(r.level)}
                      </p>
                      {evidence(r, 'req-owner task-evidence')}
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
      )}
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

export default function RequirementsExplorer({ rowsJson, metaJson }: { rowsJson: string; metaJson: string }) {
  const meta = useMemo<BoardMeta>(() => JSON.parse(metaJson), [metaJson]);
  const items = decodeRequirements(rowsJson, meta);
  const scheme = useDocumentColorScheme();
  return (
    <MantineProvider
      theme={theme}
      defaultColorScheme="auto"
      forceColorScheme={scheme === 'dark' || scheme === 'light' ? scheme : undefined}
      withCssVariables={false}
      withGlobalClasses={false}
    >
      <Explorer items={items} meta={meta} />
    </MantineProvider>
  );
}

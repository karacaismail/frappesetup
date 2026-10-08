import {
  IconAlertTriangle,
  IconApps,
  IconChartDots,
  IconChecklist,
  IconCode,
  IconFileText,
  IconHeadset,
  IconHelpCircle,
  IconHome,
  IconKey,
  IconLayoutDashboard,
  IconLayoutSidebar,
  IconLink,
  IconListCheck,
  IconMap,
  IconRoute,
  IconScale,
  IconServerCog,
  IconSettings,
  IconShieldCheck,
  IconBook2,
  IconPlug,
  IconRobot,
  IconSparkles,
  IconTools,
} from '@tabler/icons-react';
import type { IconName } from '../data/sections';

type TablerIcon = typeof IconFileText;

export const ICONS: Record<IconName, TablerIcon> = {
  home: IconHome,
  scale: IconScale,
  route: IconRoute,
  server: IconServerCog,
  settings: IconSettings,
  code: IconCode,
  layout: IconLayoutDashboard,
  key: IconKey,
  sparkles: IconSparkles,
  headset: IconHeadset,
  list: IconListCheck,
  sidebar: IconLayoutSidebar,
  apps: IconApps,
  map: IconMap,
  alert: IconAlertTriangle,
  shield: IconShieldCheck,
  link: IconLink,
  chart: IconChartDots,
  help: IconHelpCircle,
  checklist: IconChecklist,
  plug: IconPlug,
  book: IconBook2,
  robot: IconRobot,
  tools: IconTools,
  file: IconFileText,
};

export function sectionIcon(name: string | undefined): TablerIcon {
  return ICONS[(name ?? 'file') as IconName] ?? IconFileText;
}

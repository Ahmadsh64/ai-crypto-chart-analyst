import {
  Activity,
  BarChart3,
  BookOpen,
  CandlestickChart,
  Layers,
  LayoutDashboard,
  LineChart,
  ScanSearch,
  Settings,
  Target,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  description: string;
}

export const NAV_ITEMS: NavItem[] = [
  {
    label: "Overview",
    href: "/dashboard",
    icon: LayoutDashboard,
    description: "Market snapshot and system status",
  },
  {
    label: "Live Market",
    href: "/live-market",
    icon: CandlestickChart,
    description: "Real-time exchange charts",
  },
  {
    label: "AI Chart Analyzer",
    href: "/chart-analyzer",
    icon: ScanSearch,
    description: "Live + screenshot analysis workspace",
  },
  {
    label: "SMC / ICT Analysis",
    href: "/market-analysis",
    icon: Layers,
    description: "Structure, liquidity, and sessions",
  },
  {
    label: "Multi-Timeframe",
    href: "/multi-timeframe",
    icon: Activity,
    description: "4H → 5M confluence view",
  },
  {
    label: "Trade Setups",
    href: "/trade-setups",
    icon: Target,
    description: "Entry, SL, and TP plans",
  },
  {
    label: "Historical Replay",
    href: "/backtesting",
    icon: LineChart,
    description: "Deterministic multi-TF historical replay",
  },
  {
    label: "Trade Journal",
    href: "/trade-journal",
    icon: BookOpen,
    description: "Simulated trade tracking",
  },
  {
    label: "Performance",
    href: "/analytics",
    icon: BarChart3,
    description: "Simulated P&L analytics",
  },
  {
    label: "Settings",
    href: "/settings",
    icon: Settings,
    description: "Risk and preferences",
  },
];

import {
  Activity,
  BarChart3,
  BookOpen,
  CandlestickChart,
  History,
  Layers,
  LayoutDashboard,
  LineChart,
  Radar,
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
  /** When true, link is shown under Later and marked as not ready. */
  later?: boolean;
}

export interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "watch",
    label: "Watch",
    items: [
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
    ],
  },
  {
    id: "analyze",
    label: "Analyze",
    items: [
      {
        label: "AI Market Analyzer",
        href: "/chart-analyzer",
        icon: ScanSearch,
        description: "Live market intelligence + AI vision",
      },
      {
        label: "Trade Setups",
        href: "/trade-setups",
        icon: Target,
        description: "Entry, SL, TP, and risk sizing",
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
        description: "4H → 5M readiness view",
      },
    ],
  },
  {
    id: "discover",
    label: "Discover",
    items: [
      {
        label: "Market Opportunities",
        href: "/market-opportunities",
        icon: Radar,
        description: "Scanned LONG/SHORT trade ideas",
      },
    ],
  },
  {
    id: "review",
    label: "Review",
    items: [
      {
        label: "History",
        href: "/history",
        icon: History,
        description: "Saved Analyze runs from persistence",
      },
    ],
  },
  {
    id: "replay",
    label: "Replay",
    items: [
      {
        label: "Historical Replay",
        href: "/backtesting",
        icon: LineChart,
        description: "Deterministic multi-TF historical replay",
      },
    ],
  },
  {
    id: "account",
    label: "Account",
    items: [
      {
        label: "Settings",
        href: "/settings",
        icon: Settings,
        description: "Risk and preferences",
      },
    ],
  },
  {
    id: "later",
    label: "Later",
    items: [
      {
        label: "Trade Journal",
        href: "/trade-journal",
        icon: BookOpen,
        description: "Simulated trade tracking — Phase 6.0.5+",
        later: true,
      },
      {
        label: "Performance",
        href: "/analytics",
        icon: BarChart3,
        description: "Standalone metrics — use Replay for now",
        later: true,
      },
    ],
  },
];

/** Flat list for callers that do not need groups. */
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

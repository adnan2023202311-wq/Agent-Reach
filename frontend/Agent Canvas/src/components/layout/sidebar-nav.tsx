import * as React from "react";
import {
  LayoutDashboard,
  MessagesSquare,
  Bot,
  Wrench,
  Activity,
  Settings,
  Sparkles,
  ChevronsLeft,
  Workflow,
  Brain,
  Database,
  FileText,
  Store,
  FlaskConical,
  Eye,
  Hammer,
  Cloud,
  Users,
  Shield,
  CreditCard,
  Server,
  Plug,
  Globe,
  Network,
  Smartphone,
  TrendingUp,
  Cpu,
  GitBranch,
  Boxes,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/**
 * SidebarNav — presentational left navigation for the app shell.
 *
 * Router-agnostic: pass `activeId` and `onNavigate` to wire it up.
 * When pages are built with react-router, wrap items in <Link> via `renderItem`.
 */

export interface SidebarNavItem {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  badge?: string | number;
}

export const defaultSidebarItems: SidebarNavItem[] = [
  // Core workspace
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "chat", label: "Chat", icon: MessagesSquare },
  { id: "agents", label: "Agents", icon: Bot },
  { id: "agent-studio", label: "Agent Studio", icon: Hammer },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "workflows", label: "Workflows", icon: Workflow },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "knowledge", label: "Knowledge", icon: Database },
  { id: "prompts", label: "Prompts", icon: FileText },
  { id: "playground", label: "Playground", icon: FlaskConical },
  // M10: Scale & Intelligence
  { id: "distributed", label: "Distributed Cloud", icon: Cloud },
  { id: "monitoring", label: "Monitoring", icon: Activity },
  { id: "observatory", label: "Observatory", icon: Eye },
  { id: "reliability", label: "Reliability", icon: Zap },
  { id: "security", label: "Security", icon: Shield },
  { id: "billing", label: "Billing", icon: CreditCard },
  { id: "infrastructure", label: "Infrastructure", icon: Server },
  { id: "connectors", label: "Connectors", icon: Plug },
  // M10: Ecosystem
  { id: "enterprise", label: "Enterprise", icon: Users },
  { id: "marketplace", label: "Marketplace", icon: Store },
  { id: "app-store", label: "App Store", icon: Boxes },
  { id: "mobile", label: "Mobile", icon: Smartphone },
  // M10: Intelligence
  { id: "analytics", label: "Analytics", icon: TrendingUp },
  { id: "engineering", label: "Engineering", icon: Cpu },
  { id: "federation", label: "Federation", icon: Network },
  { id: "agi", label: "AGI Readiness", icon: Globe },
  // Settings
  { id: "settings", label: "Settings", icon: Settings },
];

interface SidebarNavProps {
  items?: SidebarNavItem[];
  activeId?: string;
  collapsed?: boolean;
  onNavigate?: (id: string) => void;
  onToggleCollapse?: () => void;
  className?: string;
}

export function SidebarNav({
  items = defaultSidebarItems,
  activeId,
  collapsed = false,
  onNavigate,
  onToggleCollapse,
  className,
}: SidebarNavProps) {
  return (
    <aside
      data-collapsed={collapsed}
      className={cn(
        "flex flex-col h-full bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-[width] duration-200",
        collapsed ? "w-[60px]" : "w-[232px]",
        className,
      )}
    >
      {/* Brand */}
      <div className="flex h-14 items-center gap-2.5 px-3.5 hairline-b">
        <div className="flex size-7 items-center justify-center rounded-md bg-accent/15 text-accent">
          <Sparkles size={15} />
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-foreground truncate">Agent Reach</div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Studio
            </div>
          </div>
        )}
      </div>

      {/* Items */}
      <nav className="flex-1 overflow-y-auto p-2">
        <ul className="flex flex-col gap-0.5">
          {items.map((item) => {
            const Icon = item.icon;
            const active = item.id === activeId;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onNavigate?.(item.id)}
                  aria-current={active ? "page" : undefined}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "group relative flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                    active
                      ? "bg-sidebar-accent text-foreground"
                      : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                    collapsed && "justify-center px-0",
                  )}
                >
                  {active && (
                    <span
                      aria-hidden
                      className="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-0.5 rounded-r bg-accent"
                    />
                  )}
                  <Icon size={16} className="shrink-0" />
                  {!collapsed && (
                    <>
                      <span className="flex-1 text-left truncate">{item.label}</span>
                      {item.badge != null && (
                        <span className="ml-auto rounded-md bg-surface-hover px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Collapse control */}
      <div className="p-2 hairline-t">
        <Button
          variant="ghost"
          size={collapsed ? "icon-sm" : "sm"}
          onClick={onToggleCollapse}
          className={cn("w-full", collapsed && "px-0")}
        >
          <ChevronsLeft
            size={15}
            className={cn("transition-transform", collapsed && "rotate-180")}
          />
          {!collapsed && <span>Collapse</span>}
        </Button>
      </div>
    </aside>
  );
}

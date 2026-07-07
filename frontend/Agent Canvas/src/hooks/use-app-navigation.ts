import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";

/**
 * Central router mapping for the sidebar. Every page uses `AppShell` with
 * `defaultSidebarItems`, so the wiring lives here once instead of being
 * duplicated in each route.
 *
 * Add new sidebar destinations by adding a case to `ROUTE_MAP`.
 */
const ROUTE_MAP: Record<string, string> = {
  dashboard: "/",
  chat: "/chat",
  agents: "/agents",
  "agent-studio": "/agent-studio",
  tools: "/tools",
  workflows: "/workflows",
  memory: "/memory",
  knowledge: "/knowledge",
  prompts: "/prompts",
  playground: "/playground",
  observatory: "/observatory",
  marketplace: "/marketplace",
  activity: "/observatory",
  settings: "/settings/providers",
};

export function useAppNavigation(activeId: string) {
  const navigate = useNavigate();

  return (id: string) => {
    if (id === activeId) return;
    const target = ROUTE_MAP[id];
    if (target) {
      navigate({ to: target });
    } else {
      toast(`"${id}" page coming soon`);
    }
  };
}

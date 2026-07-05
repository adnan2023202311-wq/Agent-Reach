import * as React from "react";
import { SidebarNav, type SidebarNavItem } from "@/components/layout/sidebar-nav";
import { Topbar } from "@/components/layout/topbar";
import type { ProviderOption, ModelOption } from "@/components/layout/provider-selector";
import { cn } from "@/lib/utils";

interface AppShellProps {
  sidebarItems?: SidebarNavItem[];
  activeSidebarId?: string;
  onNavigate?: (id: string) => void;

  providers: ProviderOption[];
  models: ModelOption[];
  activeProvider?: ProviderOption;
  activeModel?: ModelOption;
  onProviderChange?: (p: ProviderOption) => void;
  onModelChange?: (m: ModelOption) => void;

  children: React.ReactNode;
  className?: string;
}

/**
 * AppShell — the persistent frame around every page.
 * Composes: SidebarNav + Topbar + <main>.
 *
 * Stateless w.r.t. routing — pass `activeSidebarId` + `onNavigate` and wire to
 * react-router (or any router) at the app root.
 */
export function AppShell({
  sidebarItems,
  activeSidebarId,
  onNavigate,
  providers,
  models,
  activeProvider,
  activeModel,
  onProviderChange,
  onModelChange,
  children,
  className,
}: AppShellProps) {
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);

  // Close the mobile drawer on Escape for keyboard users.
  React.useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  return (
    <div className={cn("flex h-dvh w-full overflow-hidden bg-background", className)}>
      {/* Desktop sidebar */}
      <div className="hidden md:flex shrink-0">
        <SidebarNav
          items={sidebarItems}
          activeId={activeSidebarId}
          collapsed={collapsed}
          onNavigate={onNavigate}
          onToggleCollapse={() => setCollapsed((v) => !v)}
        />
      </div>

      {/* Mobile sidebar (overlay) */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex" role="dialog" aria-modal="true">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-background/70 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <div className="relative z-10">
            <SidebarNav
              items={sidebarItems}
              activeId={activeSidebarId}
              onNavigate={(id) => {
                onNavigate?.(id);
                setMobileOpen(false);
              }}
            />
          </div>
        </div>
      )}

      <div className="flex flex-1 flex-col min-w-0">
        <Topbar
          providers={providers}
          models={models}
          activeProvider={activeProvider}
          activeModel={activeModel}
          onProviderChange={onProviderChange}
          onModelChange={onModelChange}
          onToggleSidebar={() => setMobileOpen(true)}
        />
        <main id="main" className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}


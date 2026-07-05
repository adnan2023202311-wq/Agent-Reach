import * as React from "react";
import { Bell, Menu } from "lucide-react";
import { SearchBar } from "@/components/common/search-bar";
import { Button } from "@/components/ui/button";
import {
  ProviderSelector,
  ModelSelector,
  type ProviderOption,
  type ModelOption,
} from "@/components/layout/provider-selector";
import { cn } from "@/lib/utils";

interface TopbarProps {
  providers: ProviderOption[];
  models: ModelOption[];
  activeProvider?: ProviderOption;
  activeModel?: ModelOption;
  onProviderChange?: (p: ProviderOption) => void;
  onModelChange?: (m: ModelOption) => void;
  onToggleSidebar?: () => void;
  className?: string;
  actions?: React.ReactNode;
}

/**
 * Topbar — global header with provider + model switchers.
 *
 * Always present. The provider/model selection is application-wide state,
 * accessible from every page without opening Settings.
 */
export function Topbar({
  providers,
  models,
  activeProvider,
  activeModel,
  onProviderChange,
  onModelChange,
  onToggleSidebar,
  actions,
  className,
}: TopbarProps) {
  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-14 items-center gap-2 px-3 sm:px-4 bg-background/80 backdrop-blur-xl hairline-b",
        className,
      )}
    >
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onToggleSidebar}
        className="md:hidden"
        aria-label="Toggle sidebar"
      >
        <Menu size={16} />
      </Button>

      <div className="flex items-center gap-2">
        <ProviderSelector
          value={activeProvider}
          options={providers}
          onChange={onProviderChange}
        />
        <ModelSelector value={activeModel} options={models} onChange={onModelChange} />
      </div>

      <div className="mx-auto hidden lg:block w-full max-w-md">
        <SearchBar shortcut="⌘K" placeholder="Search chats, agents, tools…" />
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {actions}
        <Button variant="ghost" size="icon-sm" aria-label="Notifications">
          <Bell size={16} />
        </Button>
        <div
          aria-label="Account"
          className="ml-1 flex size-8 items-center justify-center rounded-full bg-accent/20 text-accent text-xs font-semibold border border-accent/30"
        >
          A
        </div>
      </div>
    </header>
  );
}

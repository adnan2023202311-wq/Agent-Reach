import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusIndicator } from "@/components/common/status-indicator";
import { cn } from "@/lib/utils";

/**
 * ProviderSelector / ModelSelector — global switchers rendered in the Topbar.
 *
 * Presentational only. State lives outside (a ProvidersContext will feed these
 * in a later step). Each dropdown is a standalone shadcn DropdownMenu.
 */

export interface ProviderOption {
  id: string;
  name: string;
  tint?: string;
  status?: "ready" | "unconfigured" | "error";
}

export interface ModelOption {
  id: string;
  name: string;
  providerId: string;
  hint?: string;
}

interface SelectorProps<T extends { id: string; name: string }> {
  value?: T;
  options: T[];
  onChange?: (option: T) => void;
  label?: string;
  placeholder?: string;
  className?: string;
  align?: "start" | "end" | "center";
}

/**
 * BaseTrigger — the visual trigger button shared by ProviderSelector and
 * ModelSelector.
 *
 * IMPORTANT (Radix `asChild` contract):
 *   `DropdownMenuTrigger asChild` clones its child and injects `ref`,
 *   `onPointerDown`, `onClick`, `onKeyDown`, `aria-haspopup`,
 *   `aria-expanded`, `data-state`, `id`, and several `data-radix-*`
 *   attributes. If the child is a plain function component that doesn't
 *   forward the ref and spread the extra props, NONE of those reach the
 *   underlying DOM <button> — Radix can't open the dropdown, can't
 *   report expanded state to assistive tech, and the chevron's
 *   `group-data-[state=open]:rotate-180` never animates.
 *
 *   The previous implementation did exactly that: it declared only
 *   `label/value/placeholder/status/className` and silently dropped
 *   everything else. Symptom: clicking the Provider trigger in the
 *   topbar did nothing, so users only ever saw the initial `value`
 *   ("Anthropic") — the dropdown never opened to reveal the rest.
 *
 *   Fix: BaseTrigger is now a `React.forwardRef` that accepts an
 *   arbitrary `...rest` prop bag and forwards both the ref and those
 *   props to the underlying <button>. This restores the Radix wiring
 *   without changing the visual API.
 */
const BaseTrigger = React.forwardRef<
  HTMLButtonElement,
  {
    label?: string;
    value?: string;
    placeholder?: string;
    status?: ProviderOption["status"];
    className?: string;
  } & React.ButtonHTMLAttributes<HTMLButtonElement>
>(function BaseTrigger(
  { label, value, placeholder, status, className, ...rest },
  ref,
) {
  const tone =
    status === "ready" ? "success" : status === "error" ? "destructive" : "warning";
  return (
    <button
      ref={ref}
      type="button"
      className={cn(
        "group inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-surface px-2.5 text-sm text-foreground transition-colors hover:bg-surface-hover hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        className,
      )}
      {...rest}
    >
      {status && <StatusIndicator tone={tone as never} size="sm" />}
      {label && (
        <span className="hidden md:inline text-xs uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
      )}
      <span className="max-w-[140px] truncate font-medium">
        {value ?? <span className="text-muted-foreground">{placeholder}</span>}
      </span>
      <ChevronDown
        size={14}
        className="text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
      />
    </button>
  );
});
BaseTrigger.displayName = "BaseTrigger";

export function ProviderSelector({
  value,
  options,
  onChange,
  className,
  align = "start",
}: SelectorProps<ProviderOption>) {
  // Diagnostic log: confirms which options array ProviderSelector
  // actually received.
  // eslint-disable-next-line no-console
  console.info(
    `[ProviderSelector] options.length=${options.length}, ids=[${options.map(o => o.id).join(", ")}], value=${value?.id ?? "none"}`,
  );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <BaseTrigger
          label="Provider"
          value={value?.name}
          placeholder="Select provider"
          status={value?.status}
          className={className}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className="w-56">
        <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
          Providers ({options.length})
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {options.map((p) => {
          const tone =
            p.status === "ready" ? "success" : p.status === "error" ? "destructive" : "warning";
          return (
            <DropdownMenuItem
              key={p.id}
              onSelect={() => onChange?.(p)}
              className="flex items-center gap-2"
            >
              <StatusIndicator tone={tone as never} size="sm" />
              <span className="flex-1">{p.name}</span>
              {value?.id === p.id && <Check size={14} className="text-accent" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ModelSelector({
  value,
  options,
  onChange,
  className,
  align = "start",
}: SelectorProps<ModelOption>) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <BaseTrigger
          label="Model"
          value={value?.name}
          placeholder="Select model"
          className={className}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className="w-64">
        <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
          Models
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {options.map((m) => (
          <DropdownMenuItem
            key={m.id}
            onSelect={() => onChange?.(m)}
            className="flex items-center gap-2"
          >
            <div className="flex-1 min-w-0">
              <div className="truncate">{m.name}</div>
              {m.hint && (
                <div className="text-[11px] text-muted-foreground truncate">{m.hint}</div>
              )}
            </div>
            {value?.id === m.id && <Check size={14} className="text-accent" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

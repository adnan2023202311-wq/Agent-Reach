import * as React from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SearchBarProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Keyboard shortcut hint shown on the right (e.g. "⌘K"). */
  shortcut?: string;
  wrapperClassName?: string;
}

export const SearchBar = React.forwardRef<HTMLInputElement, SearchBarProps>(
  ({ className, wrapperClassName, shortcut, placeholder = "Search…", ...props }, ref) => {
    return (
      <div
        className={cn(
          "group relative flex h-9 items-center rounded-lg border border-border bg-surface transition-colors focus-within:border-border-strong focus-within:bg-surface-hover",
          wrapperClassName,
        )}
      >
        <Search
          size={15}
          className="pointer-events-none absolute left-3 text-muted-foreground"
          aria-hidden
        />
        <input
          ref={ref}
          type="search"
          placeholder={placeholder}
          className={cn(
            "h-full w-full bg-transparent pl-9 pr-14 text-sm text-foreground placeholder:text-muted-foreground outline-none",
            className,
          )}
          {...props}
        />
        {shortcut && (
          <kbd
            className="pointer-events-none absolute right-2 hidden md:inline-flex h-5 items-center gap-0.5 rounded border border-border bg-background px-1.5 text-[10px] font-medium text-muted-foreground"
            aria-hidden
          >
            {shortcut}
          </kbd>
        )}
      </div>
    );
  },
);
SearchBar.displayName = "SearchBar";

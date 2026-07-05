/**
 * Shared status vocabulary used across cards, sheets, badges and lists.
 *
 * `StatusTone` maps to the palette used by `StatusIndicator` and `Badge` — it
 * intentionally mirrors those component APIs so the same value can drive both.
 */

export type StatusTone = "success" | "warning" | "destructive" | "neutral" | "info";

export interface StatusMeta {
  label: string;
  tone: StatusTone;
}

/**
 * Tailwind class helper for coloring square logo/icon tiles based on a status.
 * Kept here (not inside a component) so cards across pages stay consistent.
 */
export function tileToneClass(tone: StatusTone | "accent" | "muted"): string {
  switch (tone) {
    case "success":
      return "bg-success/15 text-success";
    case "warning":
      return "bg-warning/10 text-warning";
    case "destructive":
      return "bg-destructive/10 text-destructive";
    case "info":
      return "bg-info/15 text-info";
    case "accent":
      return "bg-accent/15 text-accent";
    case "neutral":
    case "muted":
    default:
      return "bg-surface-hover text-muted-foreground";
  }
}

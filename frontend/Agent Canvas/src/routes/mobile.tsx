import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";

export const Route = createFileRoute("/mobile")({
  component: MobilePage,
  head: () => ({ meta: [{ title: "Mobile · Agent Reach Studio" }, { name: "description", content: "Mobile companion." }] }),
});

function MobilePage() {
  const onNavigate = useAppNavigation("mobile");
  const topbar = useTopbar();

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="mobile" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.11" title="Mobile Companion" description="Native iOS and Android companion app management, push notifications, and quick actions." />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Device Registration</h3>
          <p className="text-sm text-muted-foreground">Register iOS and Android devices for push notifications and mobile access.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Push Notifications</h3>
          <p className="text-sm text-muted-foreground">Send notifications for chat completions, workflow finishes, and agent registrations.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Quick Actions</h3>
          <p className="text-sm text-muted-foreground">New chat, new conversation, view agents, marketplace, observatory — all from the home screen.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Offline Cache</h3>
          <p className="text-sm text-muted-foreground">Cache conversations and data locally for offline access. Biometric authentication supported.</p>
        </div>
      </div>
    </AppShell>
  );
}

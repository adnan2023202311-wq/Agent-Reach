import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/common/page-header";
import { defaultSidebarItems } from "@/components/layout/sidebar-nav";
import { useAppNavigation } from "@/hooks/use-app-navigation";
import { useTopbar } from "@/hooks/use-topbar";

export const Route = createFileRoute("/federation")({
  component: FederationPage,
  head: () => ({ meta: [{ title: "Federation · Agent Reach Studio" }, { name: "description", content: "AI Federation." }] }),
});

function FederationPage() {
  const onNavigate = useAppNavigation("federation");
  const topbar = useTopbar();

  return (
    <AppShell {...topbar} sidebarItems={defaultSidebarItems} activeSidebarId="federation" onNavigate={onNavigate}>
      <PageHeader eyebrow="M10.23" title="AI Federation" description="Collaborate across multiple Agent Reach installations while maintaining independent ownership and governance." />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Federation Nodes</h3>
          <p className="text-sm text-muted-foreground">Join or leave the federation. Each node maintains sovereignty while sharing agents and knowledge.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Collaboration Proposals</h3>
          <p className="text-sm text-muted-foreground">Propose sharing agents, knowledge, or collaborating on projects. Accept or reject proposals from other nodes.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Trust Levels</h3>
          <p className="text-sm text-muted-foreground">Peer, trusted, and verified trust levels with end-to-end encryption via public key exchange.</p>
        </div>
        <div className="rounded-lg border border-border bg-surface/40 p-6">
          <h3 className="text-sm font-semibold mb-2">Decentralized Governance</h3>
          <p className="text-sm text-muted-foreground">No central authority. Each installation owns its data and decides what to share.</p>
        </div>
      </div>
    </AppShell>
  );
}

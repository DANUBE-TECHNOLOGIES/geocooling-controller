import { AppShell } from "@/components/layout/AppShell";
import { DecisionPanel } from "@/components/dashboard/DecisionPanel";
import { OverviewGrid } from "@/components/dashboard/OverviewGrid";
import { SystemFlow } from "@/components/dashboard/SystemFlow";
import { mockSnapshot } from "@/lib/mock-data";

export default function Home() {
  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Vue d’ensemble</p>
          <h1>Supervision GeoCooling</h1>
          <p className="page-copy">
            État thermique, hydraulique et décisionnel de l’installation.
          </p>
        </div>
        <div className="live-pill">
          <span className="live-dot" />
          Mise à jour locale
        </div>
      </section>

      <OverviewGrid snapshot={mockSnapshot} />

      <section className="dashboard-columns">
        <DecisionPanel decision={mockSnapshot.decision} />
        <SystemFlow snapshot={mockSnapshot} />
      </section>
    </AppShell>
  );
}

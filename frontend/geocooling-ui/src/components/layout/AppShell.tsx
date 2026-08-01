import type { ReactNode } from "react";
import { MobileNav } from "@/components/layout/MobileNav";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";

type AppShellProps = {
  connected: boolean;
  mode?: string;
  refreshing?: boolean;
  lastUpdate?: Date | null;
  generatedAt?: string | null;
  responseTime?: number;
  onRefresh?: () => void;
  children: ReactNode;
};

export function AppShell({
  connected,
  mode = "unknown",
  refreshing = false,
  lastUpdate = null,
  generatedAt = null,
  responseTime = 0,
  onRefresh = () => undefined,
  children,
}: AppShellProps) {
  return (
    <div className="gc-enterprise-shell">
      <Sidebar
        connected={connected}
        mode={mode}
      />

      <div className="gc-enterprise-shell__workspace">
        <TopBar
          connected={connected}
          mode={mode}
          refreshing={refreshing}
          lastUpdate={lastUpdate}
          generatedAt={generatedAt}
          responseTime={responseTime}
          onRefresh={onRefresh}
        />

        <main className="gc-main">
          {children}
        </main>

        <footer className="gc-footer">
          <span>
            GeoCooling Controller
          </span>

          <span>
            Supervision technique locale
          </span>

          <span>
            Frontend Enterprise — UI008.1
          </span>
        </footer>
      </div>

      <MobileNav />
    </div>
  );
}

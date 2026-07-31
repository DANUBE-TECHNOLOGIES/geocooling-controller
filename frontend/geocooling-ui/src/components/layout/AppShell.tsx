import type { ReactNode } from "react";
import { TopBar } from "@/components/layout/TopBar";

type AppShellProps = {
  connected: boolean;
  mode?: string;
  refreshing?: boolean;
  lastUpdate?: Date | null;
  onRefresh?: () => void;
  children: ReactNode;
};

export function AppShell({
  connected,
  mode = "INCONNU",
  refreshing = false,
  lastUpdate = null,
  onRefresh = () => undefined,
  children,
}: AppShellProps) {
  return (
    <div className="gc-app">
      <TopBar
        connected={connected}
        mode={mode}
        refreshing={refreshing}
        lastUpdate={lastUpdate}
        onRefresh={onRefresh}
      />

      <main className="gc-main">{children}</main>

      <footer className="gc-footer">
        <span>GeoCooling Controller</span>
        <span>Supervision technique locale</span>
        <span>Frontend Enterprise V3 — Sprint F001</span>
      </footer>
    </div>
  );
}

import type { ReactNode } from "react";
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
    <div className="gc-app">
      <TopBar
        connected={connected}
        mode={mode}
        refreshing={refreshing}
        lastUpdate={lastUpdate}
        generatedAt={generatedAt}
        responseTime={responseTime}
        onRefresh={onRefresh}
      />

      <main className="gc-main">{children}</main>

      <footer className="gc-footer">
        <span>GeoCooling Controller</span>
        <span>Supervision technique locale</span>
        <span>Frontend Enterprise — UI005.1</span>
      </footer>
    </div>
  );
}

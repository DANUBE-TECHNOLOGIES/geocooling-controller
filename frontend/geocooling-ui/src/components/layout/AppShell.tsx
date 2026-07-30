import type { ReactNode } from "react";
import type { GeoCoolingMode } from "@/types/geocooling";
import { MobileNav } from "./MobileNav";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

type AppShellProps = {
  children: ReactNode;
  connected?: boolean;
  mode?: GeoCoolingMode;
};

export function AppShell({ children, connected, mode }: AppShellProps) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main">
        <Topbar connected={connected} mode={mode} />
        <main className="content">{children}</main>
      </div>
      <MobileNav />
    </div>
  );
}

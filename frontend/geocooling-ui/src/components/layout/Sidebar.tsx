"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "🏠 Dashboard" },
  { href: "/brain", label: "🧠 Brain" },
  { href: "/historian", label: "📈 Historian" },
  { href: "/forecast", label: "🌤 Prévisions" },
  { href: "/digital-twin", label: "🏗 Digital Twin" },
  { href: "/runtime", label: "⚙ Runtime" },
  { href: "/hardware", label: "🔌 Hardware" },
  { href: "/alarms", label: "🚨 Alarmes" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      style={{
        width: 250,
        background: "#111827",
        color: "#fff",
        padding: 20,
        minHeight: "100vh",
      }}
    >
      <h2 style={{ marginBottom: 30 }}>GeoCooling</h2>

      {items.map((item) => (
        <div key={item.href} style={{ marginBottom: 10 }}>
          <Link
            href={item.href}
            style={{
              color: pathname === item.href ? "#38bdf8" : "#ffffff",
              textDecoration: "none",
            }}
          >
            {item.label}
          </Link>
        </div>
      ))}
    </aside>
  );
}

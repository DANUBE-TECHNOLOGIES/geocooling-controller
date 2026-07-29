import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GeoCooling Enterprise",
  description: "Supervision intelligente du système GeoCooling",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}

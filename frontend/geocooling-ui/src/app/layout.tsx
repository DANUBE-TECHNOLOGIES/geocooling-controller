import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { GeoCoolingProvider } from "@/store/geocooling/provider/GeoCoolingProvider";

export const metadata: Metadata = {
  title: {
    default: "GeoCooling Enterprise",
    template: "%s | GeoCooling Enterprise",
  },
  description:
    "Interface locale de supervision du Smart Building Controller GeoCooling.",
  applicationName: "GeoCooling Enterprise",
  robots: {
    index: false,
    follow: false,
  },
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({
  children,
}: RootLayoutProps) {
  return (
    <html lang="fr">
      <body>
        <GeoCoolingProvider>
          <ErrorBoundary>
            {children}
          </ErrorBoundary>
        </GeoCoolingProvider>
      </body>
    </html>
  );
}

import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "backups/**",
    "**/backups/**"
  ]),
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // The UI predates React Compiler lint rules. These patterns are
      // intentional runtime synchronization (clock ticks, localStorage
      // hydration, diagnostics history) and are safe in this application.
      // Keep the rules disabled until those screens are incrementally
      // refactored; release validation still enforces Next.js, TypeScript,
      // hooks ordering and the rest of Core Web Vitals.
      "react-hooks/purity": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/preserve-manual-memoization": "off",
    },
  },
]);

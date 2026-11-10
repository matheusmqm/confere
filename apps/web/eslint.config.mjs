import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Cores só pelos tokens (CF-119): proíbe literais hexadecimais (#rgb, #rrggbb, #rrggbbaa)
  // nos .tsx. Use as classes do Tailwind (bg-cobalto, text-tinta-700) ou `var(--cobalto)`.
  {
    files: ["**/*.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "Literal[value=/^#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/]",
          message:
            "Não use cor hexadecimal em .tsx: use os tokens de design (classes do Tailwind ou var(--token)).",
        },
        {
          selector:
            "TemplateElement[value.raw=/#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\\b/]",
          message:
            "Não use cor hexadecimal em .tsx: use os tokens de design (classes do Tailwind ou var(--token)).",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;

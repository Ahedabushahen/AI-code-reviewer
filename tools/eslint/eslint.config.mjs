import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default [
  { ignores: ["**/node_modules/**", "**/dist/**", "**/build/**", "**/.next/**"] },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  // Add common globals so you don't get "console is not defined"
  {
    languageOptions: {
      globals: {
        console: "readonly",
        process: "readonly",
        module: "readonly",
        require: "readonly"
      }
    },
    rules: {
      "no-eval": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }]
    }
  }
];

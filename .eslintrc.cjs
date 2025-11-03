require("@rushstack/eslint-patch/modern-module-resolution");

module.exports = {
  root: true,
  extends: ["next/core-web-vitals", "next/typescript"],
  rules: {
    "@next/next/no-html-link-for-pages": "off",
  },
  ignorePatterns: [
    "**/node_modules/**",
    "**/.next/**",
    "**/out/**",
    "**/build/**",
    "**/next-env.d.ts",
  ],
};

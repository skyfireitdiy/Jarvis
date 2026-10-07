// ESLint 扁平配置（Flat Config，ESLint 10）
// 覆盖前端 .js / .vue 文件，使用 vue 插件的基础规则。
// 保持宽松：仅开启基础推荐规则，避免对既有代码产生大量噪声。
import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import globals from "globals";

export default [
  {
    ignores: ["dist/**", "node_modules/**"],
  },
  js.configs.recommended,
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.js", "**/*.vue"],
    languageOptions: {
      // 前端为浏览器环境，提供 window/navigator/console/Blob/URL 等全局
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      // 前端代码大量使用 console 调试，不强制 no-console
      "no-console": "off",
      "no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // 由 Vue 模板编译器处理，这里关闭模板相关报错避免误报
      "vue/multi-word-component-names": "off",
      "vue/no-v-html": "off",
    },
  },
];

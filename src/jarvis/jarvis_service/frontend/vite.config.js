import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";

// 从 package.json 读取前端版本号，构建时注入 __APP_VERSION__ 供运行时展示
const pkg = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf-8"),
);

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // 使用完整版 Vue（含运行时模板编译器），供插件前端扩展用 template 字符串渲染。
      // 插件 JS 通过 window.Vue 使用，若用 runtime-only 版则 compile 为空存根，template 无法编译。
      // 用 $ 精确匹配 `vue`，避免误伤 `vue/dist/...` 等子路径。
      "vue$": fileURLToPath(new URL("./node_modules/vue/dist/vue.esm-bundler.js", import.meta.url)),
    },
  },
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version || ""),
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
    allowedHosts: ["jarvis-front.tocmcc.cn", "jvs-ai.cn"],
  },
  test: {
    // Vue 组件测试需要 DOM 环境
    environment: "jsdom",
    // 只收 vitest 编写的用例（.test.js/.spec.js）；node:test 的 *.test.mjs
    // 由 `node --test` 负责，避免 vitest 误扫 node:test 文件而报错
    include: ["src/**/*.test.js", "src/**/*.spec.js"],
  },
});

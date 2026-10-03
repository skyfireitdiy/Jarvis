import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import { readFileSync } from "node:fs";

// 从 package.json 读取前端版本号，构建时注入 __APP_VERSION__ 供运行时展示
const pkg = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf-8"),
);

export default defineConfig({
  plugins: [vue()],
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

import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
  plugins: [vue()],
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

import { createApp } from "vue";
import * as Vue from "vue";
// 显式从完整版 Vue 导入运行时模板编译器（runtime-only 版的 compile 是空存根，
// 插件前端用 template 字符串将无法编译而渲染为空）。完整版需保留编译器，
// 故这里用具名导入并挂到 window.Vue，避免打包器 tree-shaking 摇掉。
import { compile } from "vue/dist/vue.esm-bundler.js";
import App from "./App.vue";
import "./style.css";

// 暴露全局 Vue，供插件前端扩展（运行时动态加载的 ES module）使用。
// 插件 JS 不 import 'vue'（避免 npm 模块解析），改为通过 window.Vue 使用渲染函数。
// 先实际调用一次 compile，确保打包器保留运行时模板编译器（否则 tree-shaking
// 会把 compile 内部依赖的 parse/transform 摇掉，window.Vue 上的 compile 变空存根）。
compile("<div></div>");
window.Vue = Object.assign({}, Vue, { compile });

createApp(App).mount("#app");

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((error) => {
      console.error("[PWA] Service worker registration failed:", error);
    });
  });
}

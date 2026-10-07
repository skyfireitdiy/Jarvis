import { createApp } from "vue";
import * as Vue from "vue";
import App from "./App.vue";
import "./style.css";

// 暴露全局 Vue，供插件前端扩展（运行时动态加载的 ES module）使用。
// 插件 JS 不 import 'vue'（避免 npm 模块解析），改为通过 window.Vue 使用渲染函数。
window.Vue = Vue;

createApp(App).mount("#app");

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((error) => {
      console.error("[PWA] Service worker registration failed:", error);
    });
  });
}

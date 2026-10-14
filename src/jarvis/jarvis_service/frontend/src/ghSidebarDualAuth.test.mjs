// gh 插件帮助弹层双平台认证状态回归测试。
//
// 背景：Issue #256 —— 原 refreshAuthStatus 只查询单个平台（authPlatform），
// 帮助弹层只显示一个平台的认证状态；若用户同时使用 GitHub+Gitee 双平台，
// 无法一眼看到另一个平台的登录情况。
//
// 本测试直接加载 builtin/plugins/gh/frontend/sidebar_view.js（纯浏览器 ES module，
// 导出 Vue 组件对象），验证：
//   1) refreshAuthStatus 使用 Promise.all 并发查询 github + gitee 两个平台；
//   2) authStatus 存为 { github, gitee } 结构；
//   3) 模板同时渲染 GitHub 与 Gitee 两行认证状态；
//   4) toggleHelp 不再指定单平台（双平台同时展示）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/ghSidebarDualAuth.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";

// ---- 浏览器环境桩（sidebar_view.js 顶层引用 window/localStorage/document）----
globalThis.window = { location: { protocol: "http:" }, open: () => {} };
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};
globalThis.document = { querySelector: () => null };
globalThis.fetch = async () => ({ ok: false, json: async () => ({}) });
globalThis.Vue = {};

// 从 frontend/src 相对路径指向 gh 插件前端文件（CI 的 node --test 只扫 src/**）。
const { default: comp } = await import(
  "../../../../../builtin/plugins/gh/frontend/sidebar_view.js"
);

test("组件包含双平台认证相关方法", () => {
  for (const m of [
    "toggleHelp",
    "onAuthNodeChange",
    "onAuthPlatformChange",
    "refreshAuthStatus",
  ]) {
    assert.ok(comp.methods[m], `方法 ${m} 应存在`);
  }
});

test("data 初始结构：authStatus 为 null，authLoading 为 false", () => {
  const data = comp.data();
  assert.equal(data.authStatus, null);
  assert.equal(data.authLoading, false);
});

test("模板同时渲染 GitHub 与 Gitee 两行认证状态", () => {
  assert.ok(comp.template.includes("authStatus.github"), "模板应渲染 GitHub 状态");
  assert.ok(comp.template.includes("authStatus.gitee"), "模板应渲染 Gitee 状态");
  assert.ok(
    comp.template.includes("authStatus.github.authenticated"),
    "模板应判断 GitHub 已登录",
  );
  assert.ok(
    comp.template.includes("authStatus.gitee.authenticated"),
    "模板应判断 Gitee 已登录",
  );
});

test("refreshAuthStatus 使用 Promise.all 并发查询双平台并存入 { github, gitee }", () => {
  const src = comp.methods.refreshAuthStatus.toString();
  assert.ok(src.includes("Promise.all"), "refreshAuthStatus 应使用 Promise.all 并发查询");
  assert.ok(src.includes('"github"'), "refreshAuthStatus 应查询 github 平台");
  assert.ok(src.includes('"gitee"'), "refreshAuthStatus 应查询 gitee 平台");
  assert.ok(
    src.includes("authStatus = { github"),
    "authStatus 应存为 { github, gitee } 结构",
  );
});

test("toggleHelp 不再指定单平台（双平台同时展示）", () => {
  const toggleSrc = comp.methods.toggleHelp.toString();
  assert.ok(
    !toggleSrc.includes("this.authPlatform ="),
    "toggleHelp 不应再指定单平台",
  );
});

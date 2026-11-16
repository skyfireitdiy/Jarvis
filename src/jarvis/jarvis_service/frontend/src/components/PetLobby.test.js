// PetLobby 组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/PetLobby.test.js   # 只跑本文件
//
// 说明：本组件是纯前端渲染（自绘 SVG 宠物大厅），不依赖后端接口。
// 覆盖两类需求：
// 1) daemon 与 node 分离：daemon 只能渲染为圆形接入端（is-local）一次，
//    不得以服务器机箱造型出现在节点圆周上（渲染层过滤作为防御保留）；
// 2) daemon 有独立的右键菜单：仅「打开终端」，不含网关节点动作。
import { describe, test, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import PetLobby from "./PetLobby.vue";

// jsdom 无 ResizeObserver / requestAnimationFrame，需 stub；
// 且 jsdom 的 clientWidth/clientHeight 恒为 0，需 mock 让舞台尺寸有效
function stubGlobals() {
  if (typeof globalThis.ResizeObserver === "undefined") {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  if (typeof globalThis.requestAnimationFrame === "undefined") {
    globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 16);
  }
  if (typeof globalThis.cancelAnimationFrame === "undefined") {
    globalThis.cancelAnimationFrame = clearTimeout;
  }
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() { return 1200; },
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get() { return 800; },
  });
}

// 构造 props：一个普通子节点 + master + 一个 daemon 节点（同时出现在 nodes 与 daemonSessions）
function baseProps(overrides = {}) {
  const nodes = [
    { node_id: "master", status: "online", version: "7.2.1" },
    { node_id: "node-a", status: "online", version: "7.2.1" },
    // daemon 节点：availableNodeOptions 合并进来的（带 daemon: true 标志）
    { node_id: "daemon-host-1", status: "running", daemon: true, name: "my-daemon" },
  ];
  return {
    agents: [],
    agentsLoaded: true,
    nodes,
    getStatusClass: () => "running",
    getNodeDisplayName: (id) => id,
    checkDaemonSessions: vi.fn(async () => [
      { session_id: "s1", node_id: "daemon-host-1", name: "my-daemon", platform: "linux", daemon_version: "v5.0.5" },
    ]),
    checkExtensionSessions: vi.fn(async () => []),
    ...overrides,
  };
}

describe("PetLobby daemon 去重", () => {
  beforeEach(() => {
    stubGlobals();
  });

  test("daemon 节点不渲染为服务器机箱（普通节点），仅渲染为圆形接入端一次", async () => {
    const wrapper = mount(PetLobby, { props: baseProps() });
    await flushPromises();

    // 机箱节点：普通节点（node-a）+ master；daemon 不应出现在机箱节点中
    const serverNodes = wrapper.findAll(".lobby-node:not(.is-local)");
    const nodeLabels = serverNodes.map(n => n.text()).join(" ");
    expect(nodeLabels).toContain("node-a");
    expect(nodeLabels).not.toContain("my-daemon");

    // 圆形接入端：daemon 以 is-local 渲染一次
    const localNodes = wrapper.findAll(".lobby-node.is-local");
    const localText = localNodes.map(n => n.text()).join(" ");
    expect(localText).toContain("my-daemon");
  });

  test("daemon 会话缺失时（nodes 含 daemon 但 checkDaemonSessions 返回空）不渲染任何 daemon 节点", async () => {
    const props = baseProps({ checkDaemonSessions: vi.fn(async () => []) });
    const wrapper = mount(PetLobby, { props });
    await flushPromises();

    const allText = wrapper.text();
    expect(allText).not.toContain("my-daemon");
    // 普通节点仍正常渲染
    expect(allText).toContain("node-a");
  });
});

describe("PetLobby daemon 节点右键菜单", () => {
  beforeEach(() => {
    stubGlobals();
  });

  test("daemon 节点右键弹出含「打开终端」的菜单（不含不适用动作）", async () => {
    const wrapper = mount(PetLobby, { props: baseProps() });
    await flushPromises();

    // 找到 daemon 圆形接入端节点并触发右键
    const daemonNode = wrapper.findAll(".lobby-node.is-local").find(n => n.text().includes("my-daemon"));
    expect(daemonNode).toBeTruthy();
    await daemonNode.trigger("contextmenu");

    // 菜单出现，且含「打开终端」
    const menu = wrapper.find(".lobby-context-menu");
    expect(menu.exists()).toBe(true);
    expect(menu.text()).toContain("打开终端");
    // daemon 节点不应出现「创建 Agent / 更新代码 / 重启服务 / 重命名」等网关节点动作
    expect(menu.text()).not.toContain("创建 Agent");
    expect(menu.text()).not.toContain("更新代码");
    expect(menu.text()).not.toContain("重启服务");
    expect(menu.text()).not.toContain("重命名");
    // daemon 有自己独立的菜单：只有「打开终端」一项，不与网关节点菜单共用
    const items = wrapper.findAll(".lobby-context-item");
    expect(items).toHaveLength(1);
    expect(items[0].text()).toContain("打开终端");
  });

  test("点击「打开终端」emit nodeContextRun，nodeId 为 daemon 的 node_id", async () => {
    const wrapper = mount(PetLobby, { props: baseProps() });
    await flushPromises();

    const daemonNode = wrapper.findAll(".lobby-node.is-local").find(n => n.text().includes("my-daemon"));
    await daemonNode.trigger("contextmenu");

    const openTerminalBtn = wrapper.findAll(".lobby-context-item").find(b => b.text().includes("打开终端"));
    expect(openTerminalBtn).toBeTruthy();
    await openTerminalBtn.trigger("click");

    const emitted = wrapper.emitted("nodeContextRun");
    expect(emitted).toBeTruthy();
    const { action, nodeId } = emitted[0][0];
    expect(action.id).toBe("node-open-terminal");
    expect(nodeId).toBe("daemon-host-1");
  });

  test("浏览器扩展节点右键不弹 daemon 菜单", async () => {
    const props = baseProps({
      checkExtensionSessions: vi.fn(async () => [
        { session_id: "e1", name: "chrome-ext", browser_info: { name: "Chrome" }, extension_version: "1.0.0" },
      ]),
    });
    const wrapper = mount(PetLobby, { props });
    await flushPromises();

    const extNode = wrapper.findAll(".lobby-node.is-local").find(n => n.text().includes("chrome-ext"));
    expect(extNode).toBeTruthy();
    await extNode.trigger("contextmenu");

    // 扩展节点右键不弹菜单（或弹空菜单），不包含「打开终端」
    const menu = wrapper.find(".lobby-context-menu");
    if (menu.exists()) {
      expect(menu.text()).not.toContain("打开终端");
    }
  });
});

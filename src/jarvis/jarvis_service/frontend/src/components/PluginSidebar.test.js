// PluginSidebar 的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/PluginSidebar.test.js   # 只跑本文件
//   npm run test:vitest                                   # 跑全部 vitest 用例
//
// 说明：PluginSidebar 会通过 fetchWithAuth 发起插件管理 API 请求，
// 测试中注入 mock fetchWithAuth 模拟后端响应。
import { describe, test, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import PluginSidebar from "./PluginSidebar.vue";

// 构造一个模拟的 fetchWithAuth：按 URL 返回预设响应
function makeFetch(handlers) {
  return vi.fn(async (url, options = {}) => {
    const method = options.method || "GET";
    const key = `${method} ${url}`;
    const handler = handlers[key] || handlers["default"];
    if (!handler) throw new Error(`No handler for ${key}`);
    return { json: async () => handler() };
  });
}

const plugin = (overrides = {}) => ({
  name: "demo-plugin",
  version: "0.1.0",
  description: "演示插件",
  dependencies: {
    plugins: { other: ">=1.0" },
    python: { requests: ">=2" },
    commands: ["git"],
  },
  frontend: null,
  ...overrides,
});

const baseProps = {
  fetchWithAuth: vi.fn(),
  gatewayUrl: "127.0.0.1:8000",
  showToast: vi.fn(),
  getHttpProtocol: () => "http",
  availableNodeOptions: [],
};

describe("PluginSidebar", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  test("挂载时自动加载插件列表并渲染", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [plugin()] },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("demo-plugin");
    expect(wrapper.text()).toContain("0.1.0");
    expect(wrapper.text()).toContain("演示插件");
  });

  test("空插件列表显示占位提示", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [] },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("该节点暂无已安装插件");
  });

  test("加载失败时通过 showToast 提示", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: false,
        error: { message: "权限不足" },
      }),
    });
    const showToast = vi.fn();
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth, showToast },
    });
    await flushPromises();
    expect(showToast).toHaveBeenCalledWith("权限不足", "error");
  });

  test("安装插件：填写来源后调用 install API 并刷新列表", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [] },
      }),
      "POST http://127.0.0.1:8000/api/node/master/plugins/install": () => ({
        success: true,
        data: { node_id: "master", output: [] },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper.find(".plugin-install-input").setValue("/tmp/my-plugin");
    await wrapper.find(".plugin-btn-primary").trigger("click");
    await flushPromises();
    // 安装成功应调用 install API
    const installCall = fetchWithAuth.mock.calls.find(
      ([url, opt]) =>
        opt?.method === "POST" && url.includes("/api/node/master/plugins/install"),
    );
    expect(installCall).toBeTruthy();
    const body = JSON.parse(installCall[1].body);
    expect(body.source).toBe("/tmp/my-plugin");
    expect(body.force).toBe(false);
  });

  test("卸载插件：确认后调用 uninstall API", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [plugin()] },
      }),
      "POST http://127.0.0.1:8000/api/node/master/plugins/demo-plugin/uninstall": () => ({
        success: true,
        data: { node_id: "master", output: [] },
      }),
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper.findAll(".plugin-btn-danger")[0].trigger("click");
    await flushPromises();
    const uninstallCall = fetchWithAuth.mock.calls.find(
      ([url, opt]) => opt?.method === "POST" && url.includes("/uninstall"),
    );
    expect(uninstallCall).toBeTruthy();
    expect(uninstallCall[0]).toContain("/api/node/master/plugins/demo-plugin/uninstall");
    confirmSpy.mockRestore();
  });

  test("升级插件：确认后调用 upgrade API", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [plugin()] },
      }),
      "POST http://127.0.0.1:8000/api/node/master/plugins/demo-plugin/upgrade": () => ({
        success: true,
        data: { node_id: "master", output: [] },
      }),
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper
      .find(".plugin-btn-sm:not(.plugin-btn-danger)")
      .trigger("click");
    await flushPromises();
    const upgradeCall = fetchWithAuth.mock.calls.find(
      ([url, opt]) => opt?.method === "POST" && url.includes("/upgrade"),
    );
    expect(upgradeCall).toBeTruthy();
    expect(upgradeCall[0]).toContain("/api/node/master/plugins/demo-plugin/upgrade");
    confirmSpy.mockRestore();
  });

  test("内置插件不显示升级/卸载按钮，并显示内置标记", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: {
          node_id: "master",
          plugins: [plugin({ name: "builtin-p", builtin: true })],
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("内置");
    expect(wrapper.find(".plugin-item-actions").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("升级");
    expect(wrapper.text()).not.toContain("卸载");
  });

  test("能力不显示在条目中，鼠标悬浮时通过悬浮框展示", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: {
          node_id: "master",
          plugins: [
            plugin({
              capabilities: [
                { name: "事件钩子 on_task_start", description: "任务开始触发" },
                { name: "@mycmd", description: "内置命令" },
              ],
            }),
          ],
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    // 能力不应占用条目空间（条目中不渲染能力文本）
    expect(wrapper.find(".plugin-item-capabilities").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("事件钩子 on_task_start");
    expect(wrapper.text()).not.toContain("@mycmd");
    // 悬浮框初始不渲染
    expect(wrapper.find(".plugin-cap-tooltip").exists()).toBe(false);
    // 鼠标悬浮到插件条目时展示能力悬浮框
    await wrapper.find(".plugin-item").trigger("mouseenter");
    expect(wrapper.find(".plugin-cap-tooltip").exists()).toBe(true);
    expect(wrapper.text()).toContain("事件钩子 on_task_start");
    expect(wrapper.text()).toContain("任务开始触发");
    expect(wrapper.text()).toContain("@mycmd");
    expect(wrapper.text()).toContain("内置命令");
  });
});

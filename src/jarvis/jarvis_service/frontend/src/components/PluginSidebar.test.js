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
  // 复用全局确认弹窗：测试中自动执行确认回调，模拟用户点「确认」
  showConfirm: (_message, confirmCallback) => confirmCallback(),
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

  test("插件描述渲染带 title 属性以支持悬停查看完整内容", async () => {
    const longDesc = "这是一个非常长的插件描述，用于验证描述被截断后仍可通过悬停查看完整内容。".repeat(3);
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [plugin({ description: longDesc })] },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    const desc = wrapper.find(".plugin-item-desc");
    expect(desc.exists()).toBe(true);
    // title 属性携带完整描述，悬停可查看完整内容
    expect(desc.attributes("title")).toBe(longDesc);
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

  test("卸载插件：右键菜单中点击卸载，确认后调用 uninstall API", async () => {
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
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    // 列表项上不再直接显示卸载按钮
    expect(wrapper.find(".plugin-btn-danger").exists()).toBe(false);
    // 右键打开菜单，点击「卸载」菜单项
    await wrapper.find(".plugin-item").trigger("contextmenu");
    await wrapper.find(".plugin-cap-menu-item-danger").trigger("click");
    await flushPromises();
    // 点击卸载后菜单关闭
    expect(wrapper.find(".plugin-cap-menu").exists()).toBe(false);
    const uninstallCall = fetchWithAuth.mock.calls.find(
      ([url, opt]) => opt?.method === "POST" && url.includes("/uninstall"),
    );
    expect(uninstallCall).toBeTruthy();
    expect(uninstallCall[0]).toContain("/api/node/master/plugins/demo-plugin/uninstall");
  });

  test("升级插件：确认后调用 upgrade API", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [plugin({ hasUpdate: true })] },
      }),
      "POST http://127.0.0.1:8000/api/node/master/plugins/demo-plugin/upgrade": () => ({
        success: true,
        data: { node_id: "master", output: [] },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper
      .find(".plugin-update-btn")
      .trigger("click");
    await flushPromises();
    const upgradeCall = fetchWithAuth.mock.calls.find(
      ([url, opt]) => opt?.method === "POST" && url.includes("/upgrade"),
    );
    expect(upgradeCall).toBeTruthy();
    expect(upgradeCall[0]).toContain("/api/node/master/plugins/demo-plugin/upgrade");
  });

  test("内置插件不显示升级按钮，右键菜单无卸载项，并显示内置标记", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: {
          node_id: "master",
          plugins: [plugin({ name: "builtin-p", builtin: true, hasUpdate: true })],
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("内置");
    // 内置插件不显示更新按钮
    expect(wrapper.find(".plugin-update-btn").exists()).toBe(false);
    // 右键菜单对内置插件仍可用，但无「卸载」项
    await wrapper.find(".plugin-item").trigger("contextmenu");
    expect(wrapper.find(".plugin-cap-menu").exists()).toBe(true);
    expect(wrapper.find(".plugin-cap-menu-item-danger").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("卸载");
  });

  test("能力不显示在条目中，右键菜单弹出能力详情弹窗展示", async () => {
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
    // 右键菜单初始不渲染
    expect(wrapper.find(".plugin-cap-menu").exists()).toBe(false);
    // 右键点击插件条目时展示右键菜单
    await wrapper.find(".plugin-item").trigger("contextmenu");
    expect(wrapper.find(".plugin-cap-menu").exists()).toBe(true);
    expect(wrapper.text()).toContain("能力详情");
    // 非内置插件右键菜单同时提供「卸载」项
    expect(wrapper.find(".plugin-cap-menu-item-danger").exists()).toBe(true);
    // 点击“能力详情”弹出弹窗，展示全部能力
    await wrapper.find(".plugin-cap-menu-item").trigger("click");
    expect(wrapper.find(".cap-modal").exists()).toBe(true);
    expect(wrapper.text()).toContain("事件钩子 on_task_start");
    expect(wrapper.text()).toContain("任务开始触发");
    expect(wrapper.text()).toContain("@mycmd");
    expect(wrapper.text()).toContain("内置命令");
  });

  test("无能力的插件右键菜单仍可用，仅提供卸载项", async () => {
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
    // 无 capabilities 的插件右键仍能弹出菜单
    await wrapper.find(".plugin-item").trigger("contextmenu");
    expect(wrapper.find(".plugin-cap-menu").exists()).toBe(true);
    // 无能力详情项，但有卸载项
    expect(wrapper.text()).not.toContain("能力详情");
    expect(wrapper.find(".plugin-cap-menu-item-danger").exists()).toBe(true);
  });

  test("市场 tab：切换后加载市场插件并渲染", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [] },
      }),
      "GET http://127.0.0.1:8000/api/plugins/market": () => ({
        success: true,
        data: {
          plugins: [
            {
              id: "market-p",
              name: "市场插件",
              description: "来自市场的插件",
              repo: "https://github.com/owner/market-p",
              branch: "main",
              author: "作者甲",
              categories: ["工具", "效率"],
            },
          ],
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    // 默认在已安装 tab，不显示市场内容
    expect(wrapper.find(".plugin-market").exists()).toBe(false);
    // 切换到市场 tab
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    expect(wrapper.find(".plugin-market").exists()).toBe(true);
    expect(wrapper.text()).toContain("市场插件");
    expect(wrapper.text()).toContain("来自市场的插件");
    expect(wrapper.text()).toContain("作者甲");
    expect(wrapper.text()).toContain("工具");
  });

  test("市场 tab：从市场安装插件用 repo#branch 构造 source", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [] },
      }),
      "GET http://127.0.0.1:8000/api/plugins/market": () => ({
        success: true,
        data: {
          plugins: [
            {
              id: "market-p",
              name: "市场插件",
              repo: "https://github.com/owner/market-p",
              branch: "main",
            },
          ],
        },
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
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    // 点击市场插件的安装按钮
    await wrapper.find(".plugin-market-item .plugin-btn-primary").trigger("click");
    await flushPromises();
    const installCall = fetchWithAuth.mock.calls.find(
      ([url, opt]) =>
        opt?.method === "POST" && url.includes("/api/node/master/plugins/install"),
    );
    expect(installCall).toBeTruthy();
    const body = JSON.parse(installCall[1].body);
    expect(body.source).toBe("https://github.com/owner/market-p#main");
  });

  test("市场 tab：显示节点选择器，可安装到指定子节点", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [] },
      }),
      "GET http://127.0.0.1:8000/api/plugins/market": () => ({
        success: true,
        data: {
          plugins: [
            {
              id: "market-p",
              name: "市场插件",
              repo: "https://github.com/owner/market-p",
              branch: "main",
            },
          ],
        },
      }),
      "POST http://127.0.0.1:8000/api/node/child-1/plugins/install": () => ({
        success: true,
        data: { node_id: "child-1", output: [] },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: {
        ...baseProps,
        fetchWithAuth,
        availableNodeOptions: [
          { node_id: "child-1", status: "running", label: "子节点1" },
        ],
      },
    });
    await flushPromises();
    // 切到市场 tab
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    // 市场页也应显示节点选择器
    expect(wrapper.find(".plugin-node-select").exists()).toBe(true);
    // 选择子节点
    await wrapper.find(".plugin-node-select-input").setValue("child-1");
    // 点击市场插件的安装按钮
    await wrapper.find(".plugin-market-item .plugin-btn-primary").trigger("click");
    await flushPromises();
    const installCall = fetchWithAuth.mock.calls.find(
      ([url, opt]) =>
        opt?.method === "POST" && url.includes("/api/node/child-1/plugins/install"),
    );
    expect(installCall).toBeTruthy();
  });
});

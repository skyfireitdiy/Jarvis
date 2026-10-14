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
// handler key 用 "METHOD path"（不含 query 部分），query 参数单独匹配
function makeFetch(handlers) {
  return vi.fn(async (url, options = {}) => {
    const method = options.method || "GET";
    const [path] = url.split("?");
    const key = `${method} ${path}`;
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

  test("市场 tab：已安装插件显示「已安装」徽章，不显示安装按钮", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: {
          node_id: "master",
          plugins: [
            plugin({ name: "market-p", version: "0.1.0" }),
            plugin({ name: "other-plugin", version: "0.1.0" }),
          ],
        },
      }),
      "GET http://127.0.0.1:8000/api/plugins/market": () => ({
        success: true,
        data: {
          plugins: [
            {
              id: "market-p",
              name: "market-p",
              repo: "https://github.com/owner/market-p",
              branch: "main",
              installed: true,
            },
            {
              id: "not-installed",
              name: "未安装插件",
              repo: "https://github.com/owner/not-installed",
              branch: "main",
              installed: false,
            },
          ],
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    const items = wrapper.findAll(".plugin-market-item");
    expect(items).toHaveLength(2);
    // 已安装插件：显示「已安装」徽章，无安装按钮
    expect(items[0].text()).toContain("已安装");
    expect(items[0].find(".plugin-btn-primary").exists()).toBe(false);
    // 未安装插件：显示安装按钮，无「已安装」徽章
    expect(items[1].text()).not.toContain("已安装");
    expect(items[1].find(".plugin-btn-primary").exists()).toBe(true);
  });

  test("市场 tab：未勾选「只看已安装」也始终传 installed_names 供后端打标记", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: {
          node_id: "master",
          plugins: [plugin({ name: "market-p", version: "0.1.0" })],
        },
      }),
      "GET http://127.0.0.1:8000/api/plugins/market": () => ({
        success: true,
        data: {
          plugins: [
            {
              id: "market-p",
              name: "market-p",
              repo: "https://github.com/owner/market-p",
              branch: "main",
              installed: true,
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          total_pages: 1,
          filters: { categories: [], market_repos: [] },
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    const marketCall = fetchWithAuth.mock.calls.find(
      ([url]) => url.includes("/api/plugins/market"),
    );
    expect(marketCall).toBeTruthy();
    // 未勾选「只看已安装」：不应带 installed=true
    expect(marketCall[0]).not.toContain("installed=true");
    // 但始终带 installed_names
    expect(marketCall[0]).toContain("installed_names=market-p");
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

  test("市场 tab：加载时带分页参数并渲染总数/分页信息", async () => {
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
              id: "p1",
              name: "插件1",
              repo: "https://github.com/owner/p1",
              branch: "main",
            },
            {
              id: "p2",
              name: "插件2",
              repo: "https://github.com/owner/p2",
              branch: "main",
            },
          ],
          total: 25,
          page: 1,
          page_size: 20,
          total_pages: 2,
          filters: {
            categories: ["工具", "集成"],
            market_repos: ["https://github.com/orgA/market"],
          },
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    // 请求 URL 带分页参数
    const marketCall = fetchWithAuth.mock.calls.find(
      ([url]) => url.includes("/api/plugins/market"),
    );
    expect(marketCall).toBeTruthy();
    expect(marketCall[0]).toContain("page=1");
    expect(marketCall[0]).toContain("page_size=20");
    // 渲染分页信息
    expect(wrapper.text()).toContain("第 1 / 2 页");
    expect(wrapper.text()).toContain("共 25 个");
    // 分类下拉选项渲染
    expect(wrapper.find(".plugin-market-filter").exists()).toBe(true);
  });

  test("市场 tab：搜索关键字触发带 keyword 的请求", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [] },
      }),
      "GET http://127.0.0.1:8000/api/plugins/market": () => ({
        success: true,
        data: {
          plugins: [],
          total: 0,
          page: 1,
          page_size: 20,
          total_pages: 1,
          filters: { categories: [], market_repos: [] },
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    // 输入关键字触发重新加载
    await wrapper.find(".plugin-market-search").setValue("数据库");
    await flushPromises();
    const marketCalls = fetchWithAuth.mock.calls.filter(
      ([url]) => url.includes("/api/plugins/market"),
    );
    const lastCall = marketCalls[marketCalls.length - 1];
    const decoded = decodeURIComponent(lastCall[0]);
    expect(decoded).toContain("keyword=数据库");
    expect(decoded).toContain("page=1");
  });

  test("市场 tab：点击下一页加载 page=2", async () => {
    let page = 1;
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: { node_id: "master", plugins: [] },
      }),
      "GET http://127.0.0.1:8000/api/plugins/market": () => ({
        success: true,
        data: {
          plugins:
            page === 1
              ? [
                  {
                    id: "p1",
                    name: "插件1",
                    repo: "https://github.com/owner/p1",
                    branch: "main",
                  },
                ]
              : [
                  {
                    id: "p21",
                    name: "插件21",
                    repo: "https://github.com/owner/p21",
                    branch: "main",
                  },
                ],
          total: 25,
          page,
          page_size: 20,
          total_pages: 2,
          filters: { categories: [], market_repos: [] },
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("插件1");
    // 点击下一页
    page = 2;
    const nextBtn = wrapper.findAll(".plugin-market-pagination button").find(
      (b) => b.text() === "下一页",
    );
    await nextBtn.trigger("click");
    await flushPromises();
    const marketCalls = fetchWithAuth.mock.calls.filter(
      ([url]) => url.includes("/api/plugins/market"),
    );
    expect(marketCalls[marketCalls.length - 1][0]).toContain("page=2");
    expect(wrapper.text()).toContain("插件21");
  });

  test("市场 tab：勾选只看已安装时带 installed 参数", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/node/master/plugins": () => ({
        success: true,
        data: {
          node_id: "master",
          plugins: [{ name: "插件1" }, { name: "插件2" }],
        },
      }),
      "GET http://127.0.0.1:8000/api/plugins/market": () => ({
        success: true,
        data: {
          plugins: [],
          total: 0,
          page: 1,
          page_size: 20,
          total_pages: 1,
          filters: { categories: [], market_repos: [] },
        },
      }),
    });
    const wrapper = mount(PluginSidebar, {
      props: { ...baseProps, fetchWithAuth },
    });
    await flushPromises();
    await wrapper.findAll(".plugin-sidebar-tab")[1].trigger("click");
    await flushPromises();
    // 勾选"只看已安装"
    await wrapper
      .find(".plugin-market-installed-label input[type='checkbox']")
      .setValue(true);
    await flushPromises();
    const marketCalls = fetchWithAuth.mock.calls.filter(
      ([url]) => url.includes("/api/plugins/market"),
    );
    const lastCall = marketCalls[marketCalls.length - 1];
    const decoded = decodeURIComponent(lastCall[0]);
    expect(decoded).toContain("installed=true");
    expect(decoded).toContain("installed_names=插件1,插件2");
  });
});

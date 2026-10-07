// pluginExtensions.js 的单元测试（vitest）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/pluginExtensions.test.js   # 只跑本文件
//   npm run test:vitest                           # 跑全部 vitest 用例
import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";
import {
  fetchPluginExtensions,
  buildExtensionUrl,
  loadExtensionComponent,
  clearExtensionCache,
} from "./pluginExtensions.js";

// 构造一个模拟的 fetchWithAuth：按 URL 返回预设响应
function makeFetch(handlers) {
  return vi.fn(async (url, options = {}) => {
    const method = options.method || "GET";
    const key = `${method} ${url}`;
    const handler = handlers[key] || handlers["default"];
    if (!handler) throw new Error(`No handler for ${key}`);
    return { ok: true, json: async () => handler() };
  });
}

const baseOpts = {
  fetchWithAuth: vi.fn(),
  baseUrl: "127.0.0.1:8000",
  getHttpProtocol: () => "http",
};

describe("fetchPluginExtensions", () => {
  test("解析各插件 frontend 扩展点并生成扩展清单项", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/plugins?node_id=master": () => ({
        success: true,
        data: {
          node_id: "master",
          plugins: [
            {
              name: "demo",
              version: "0.1.0",
              frontend: {
                admin_tabs: [
                  { id: "dashboard", title: "仪表盘", entry: "admin.js" },
                ],
                sidebar_views: [
                  { id: "stats", title: "统计", entry: "side.js" },
                ],
                tool_panels: [{ id: "tool1", title: "工具", entry: "tool.js" }],
              },
            },
          ],
        },
      }),
    });

    const exts = await fetchPluginExtensions({ ...baseOpts, fetchWithAuth });
    expect(exts).toHaveLength(3);
    const admin = exts.find((e) => e.extType === "admin_tabs");
    expect(admin).toMatchObject({
      nodeId: "master",
      plugin: "demo",
      pluginVersion: "0.1.0",
      extType: "admin_tabs",
      id: "dashboard",
      title: "仪表盘",
      entry: "admin.js",
    });
    expect(admin.url).toBe(
      "http://127.0.0.1:8000/api/plugins/master/demo/frontend/admin.js",
    );
    expect(exts.find((e) => e.extType === "sidebar_views").id).toBe("stats");
    expect(exts.find((e) => e.extType === "tool_panels").id).toBe("tool1");
  });

  test("无 frontend 声明或无效项时跳过", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/plugins?node_id=master": () => ({
        success: true,
        data: {
          node_id: "master",
          plugins: [
            { name: "a", version: "1", frontend: null },
            {
              name: "b",
              version: "1",
              frontend: { admin_tabs: [{ title: "no id" }] },
            },
            {
              name: "c",
              version: "1",
              frontend: { admin_tabs: [{ id: "x", entry: "" }] },
            },
          ],
        },
      }),
    });

    const exts = await fetchPluginExtensions({ ...baseOpts, fetchWithAuth });
    expect(exts).toHaveLength(0);
  });

  test("请求失败或响应不成功时返回空数组", async () => {
    const fetchWithAuth = vi.fn(async () => ({ ok: false }));
    const exts = await fetchPluginExtensions({ ...baseOpts, fetchWithAuth });
    expect(exts).toEqual([]);
  });

  test("异常时静默返回空数组", async () => {
    const fetchWithAuth = vi.fn(async () => {
      throw new Error("network down");
    });
    const exts = await fetchPluginExtensions({ ...baseOpts, fetchWithAuth });
    expect(exts).toEqual([]);
  });
});

describe("buildExtensionUrl", () => {
  test("构造 serve 端点 URL（去前导斜杠、编码节点与插件名）", () => {
    const url = buildExtensionUrl({
      nodeId: "node/1",
      plugin: "my plugin",
      entry: "/admin.js",
      baseUrl: "127.0.0.1:8000",
      getHttpProtocol: () => "http",
    });
    expect(url).toBe(
      "http://127.0.0.1:8000/api/plugins/node%2F1/my%20plugin/frontend/admin.js",
    );
  });
});

describe("loadExtensionComponent", () => {
  beforeEach(() => {
    clearExtensionCache();
  });
  afterEach(() => {
    clearExtensionCache();
  });

  test("从后端拉取 JS 源码并经 Blob import 得到组件 default export", async () => {
    // 用 data URL 作为 createObjectURL 的返回值，使 node 环境的动态 import 真实可执行
    globalThis.Blob = vi.fn(function (parts) {
      return { parts };
    });
    globalThis.URL.createObjectURL = vi.fn(
      () =>
        "data:text/javascript,export default { name: 'FakeExt', render() {} }",
    );
    globalThis.URL.revokeObjectURL = vi.fn();

    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/plugins/master/demo/frontend/admin.js":
        () => ({
          success: true,
          data: {
            node_id: "master",
            name: "demo",
            content: "export default {}",
          },
        }),
    });

    const ext = {
      nodeId: "master",
      plugin: "demo",
      extType: "admin_tabs",
      id: "dashboard",
      entry: "admin.js",
      url: "http://127.0.0.1:8000/api/plugins/master/demo/frontend/admin.js",
    };

    const comp = await loadExtensionComponent(ext, {
      fetchWithAuth,
      getHttpProtocol: () => "http",
    });
    expect(comp).toBeTruthy();
    expect(comp.name).toBe("FakeExt");
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });

  test("响应无 content 或失败时返回 null", async () => {
    const fetchWithAuth = makeFetch({
      "GET http://127.0.0.1:8000/api/plugins/master/demo/frontend/admin.js":
        () => ({
          success: true,
          data: { content: "" },
        }),
    });
    const ext = {
      nodeId: "master",
      plugin: "demo",
      extType: "admin_tabs",
      id: "dashboard",
      entry: "admin.js",
      url: "http://127.0.0.1:8000/api/plugins/master/demo/frontend/admin.js",
    };
    const comp = await loadExtensionComponent(ext, {
      fetchWithAuth,
      getHttpProtocol: () => "http",
    });
    expect(comp).toBeNull();
  });

  test("同 key 组件缓存复用", async () => {
    let calls = 0;
    const fetchWithAuth = vi.fn(async () => {
      calls += 1;
      return {
        ok: true,
        json: async () => ({
          success: true,
          data: { content: "export default 1" },
        }),
      };
    });
    const ext = {
      nodeId: "master",
      plugin: "demo",
      extType: "admin_tabs",
      id: "dashboard",
      entry: "admin.js",
      url: "http://127.0.0.1:8000/api/plugins/master/demo/frontend/admin.js",
    };
    // 第一次：mock Blob/URL，createObjectURL 返回可真实 import 的 data URL
    globalThis.Blob = vi.fn(function () {
      return {};
    });
    globalThis.URL.createObjectURL = vi.fn(
      () => "data:text/javascript,export default { name: 'C' }",
    );
    globalThis.URL.revokeObjectURL = vi.fn();

    const c1 = await loadExtensionComponent(ext, {
      fetchWithAuth,
      getHttpProtocol: () => "http",
    });
    const c2 = await loadExtensionComponent(ext, {
      fetchWithAuth,
      getHttpProtocol: () => "http",
    });
    expect(c1).toBe(c2);
    // 缓存命中后不再重复 fetch
    expect(calls).toBe(1);
  });
});

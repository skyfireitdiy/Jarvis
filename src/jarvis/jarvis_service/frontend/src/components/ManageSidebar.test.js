// ManageSidebar 的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/ManageSidebar.test.js   # 只跑本文件
//   npm run test:vitest                                   # 跑全部 vitest 用例
//
// 说明：ManageSidebar 是纯展示型组件——由 props 驱动渲染，自身不发起请求、
// 无写操作，故可直接 mount 测试，无需 mock 网络。
import { describe, test, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ManageSidebar from "./ManageSidebar.vue";

// 构造定时任务
function timer(overrides = {}) {
  return {
    task_id: "task-12345678",
    run_at: "2026-10-02T12:00:00",
    interval_seconds: null,
    is_recurring: false,
    cancelled: false,
    metadata: {
      action: { type: "capability_call", params: { name: "system.info" } },
      schedule: { type: "run_at", run_at: "2026-10-02T12:00:00" },
    },
    ...overrides,
  };
}

// 构造 daemon 会话
function session(overrides = {}) {
  return {
    session_id: "sess-abc",
    name: "my-pc",
    hostname: "my-pc",
    platform: "windows",
    daemon_version: "v6.0.1",
    capabilities: [
      {
        name: "system.info",
        description: "查询系统信息",
        parameters: { type: "object", properties: {} },
        platform: "any",
      },
    ],
    ...overrides,
  };
}

// 构造浏览器扩展会话
function extensionSession(overrides = {}) {
  return {
    session_id: "ext-xyz",
    name: "Chrome 扩展",
    extension_version: "v1.2.3",
    browser_info: { name: "Chrome", version: "120", os: "Windows" },
    tabs: [{ tab_id: 1, title: "示例页", url: "https://example.com" }],
    capabilities: [
      {
        name: "script.execute",
        description: "在页面执行任意 JS 脚本（主世界）",
        parameters: { code: "string" },
        platform: "browser",
      },
      {
        name: "tab.create",
        description: "新建标签页",
        parameters: { url: "string" },
        platform: "browser",
      },
    ],
    ...overrides,
  };
}

function mountSidebar(props = {}) {
  return mount(ManageSidebar, {
    props: {
      view: "manage",
      timers: [],
      daemonSessions: [],
      extensionSessions: [],
      installedScripts: [],
      gatewayScripts: [],
      ...props,
    },
  });
}

describe("ManageSidebar 定时任务展示（view=timers）", () => {
  test("定时任务视图，空态提示", () => {
    const wrapper = mountSidebar({ view: "timers" });
    expect(wrapper.find(".manage-sidebar-title").text()).toBe("定时任务");
    expect(wrapper.find(".manage-sidebar-empty").text()).toContain(
      "暂无定时任务",
    );
  });

  test("定时任务视图不显示刷新按钮", () => {
    const wrapper = mountSidebar({ view: "timers" });
    expect(wrapper.find(".manage-sidebar-refresh").exists()).toBe(false);
  });

  test("渲染定时任务列表（动作类型/状态/调度）", () => {
    const wrapper = mountSidebar({ view: "timers", timers: [timer()] });
    expect(wrapper.find(".manage-timer-item").exists()).toBe(true);
    expect(wrapper.find(".manage-timer-type").text()).toBe("调用能力");
    expect(wrapper.find(".manage-timer-status").text()).toBe("运行中");
    expect(wrapper.find(".manage-timer-schedule").text()).toContain("定时");
  });

  test("已取消任务显示取消状态", () => {
    const wrapper = mountSidebar({
      view: "timers",
      timers: [timer({ cancelled: true })],
    });
    expect(wrapper.find(".manage-timer-status").text()).toBe("已取消");
    expect(wrapper.find(".manage-timer-status").classes()).toContain(
      "cancelled",
    );
  });

  test("cron 调度显示 cron 表达式", () => {
    const wrapper = mountSidebar({
      view: "timers",
      timers: [
        timer({
          metadata: {
            action: { type: "capability_call" },
            schedule: { type: "cron", cron: "0 9 * * 1" },
          },
        }),
      ],
    });
    expect(wrapper.find(".manage-timer-schedule").text()).toContain(
      "cron: 0 9 * * 1",
    );
  });

  test("动作类型未知时显示原始类型", () => {
    const wrapper = mountSidebar({
      view: "timers",
      timers: [timer({ metadata: { action: { type: "custom_action" } } })],
    });
    expect(wrapper.find(".manage-timer-type").text()).toBe("custom_action");
  });
});

describe("ManageSidebar 能力清单展示（view=manage）", () => {
  test("能力清单视图标题与刷新按钮", () => {
    const wrapper = mountSidebar();
    expect(wrapper.find(".manage-sidebar-title").text()).toBe("增强能力清单");
    expect(wrapper.find(".manage-sidebar-refresh").exists()).toBe(true);
  });

  test("无任何能力时提示暂无可用能力", () => {
    const wrapper = mountSidebar();
    expect(wrapper.find(".manage-sidebar-empty").text()).toContain(
      "暂无可用能力",
    );
  });

  test("点击刷新按钮触发 refresh 事件", async () => {
    const wrapper = mountSidebar({ daemonSessions: [session()] });
    await wrapper.find(".manage-sidebar-refresh").trigger("click");
    expect(wrapper.emitted("refresh")).toBeTruthy();
  });

  test("展示 daemon 会话与能力", async () => {
    const wrapper = mountSidebar({ daemonSessions: [session()] });
    expect(wrapper.find(".manage-section-title").text()).toBe("Daemon 能力");
    expect(wrapper.find(".manage-session-name").text()).toBe("my-pc");
    // 展开会话后能力列表可见
    await wrapper.find(".manage-session-head").trigger("click");
    expect(wrapper.find(".manage-capability-name").text()).toBe("system.info");
  });

  test("展开 daemon 会话后可查看能力详情（描述与参数）", async () => {
    const wrapper = mountSidebar({ daemonSessions: [session()] });
    // 展开会话
    await wrapper.find(".manage-session-head").trigger("click");
    // 展开能力后可见描述与参数
    await wrapper.find(".manage-capability-head").trigger("click");
    expect(wrapper.find(".manage-capability-desc").text()).toContain(
      "查询系统信息",
    );
    expect(wrapper.find(".manage-capability-params-json").exists()).toBe(true);
  });

  test("展示浏览器扩展会话及其能力清单", async () => {
    const wrapper = mountSidebar({ extensionSessions: [extensionSession()] });
    expect(wrapper.find(".manage-section-title").text()).toBe("浏览器扩展");
    expect(wrapper.find(".manage-session-name").text()).toBe("Chrome 扩展");
    // 展开扩展会话后可见浏览器信息与能力清单
    await wrapper.find(".manage-session-head").trigger("click");
    expect(wrapper.find(".manage-capability-desc").text()).toContain("Chrome");
    expect(wrapper.find(".manage-capability-name").text()).toBe(
      "script.execute",
    );
  });

  test("展开浏览器扩展能力后可查看详情（描述与参数）", async () => {
    const wrapper = mountSidebar({ extensionSessions: [extensionSession()] });
    await wrapper.find(".manage-session-head").trigger("click");
    await wrapper.find(".manage-capability-head").trigger("click");
    expect(
      wrapper.find(".manage-capability-body .manage-capability-desc").text(),
    ).toContain("在页面执行任意 JS 脚本");
    expect(wrapper.find(".manage-capability-params-json").exists()).toBe(true);
  });

  test("浏览器扩展会话展开后显示已安装脚本", async () => {
    const wrapper = mountSidebar({
      extensionSessions: [extensionSession()],
      installedScripts: [
        {
          session_id: "ext-xyz",
          name: "Chrome 扩展",
          scripts: [
            {
              id: "s-1",
              name: "mysite",
              description: "某站点文档操作",
              version: "1.0.0",
              enabled: true,
              match: ["https://example.com/*"],
            },
          ],
        },
      ],
    });
    await wrapper.find(".manage-session-head").trigger("click");
    expect(wrapper.find(".manage-script-name").text()).toBe("mysite");
    expect(wrapper.find(".manage-script-desc").text()).toContain(
      "某站点文档操作",
    );
    expect(wrapper.find(".manage-script-status").text()).toBe("已启用");
  });

  test("展示网关脚本库", () => {
    const wrapper = mountSidebar({
      gatewayScripts: [
        { name: "backup", size: 2048, updated_at: "2026-10-02T00:00:00" },
      ],
    });
    expect(wrapper.find(".manage-section-title").text()).toBe("网关脚本库");
    expect(wrapper.find(".manage-script-name").text()).toBe("backup");
    expect(wrapper.find(".manage-script-status").text()).toBe("2.0 KB");
  });
});

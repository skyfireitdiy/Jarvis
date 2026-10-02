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

function mountSidebar(props = {}) {
  return mount(ManageSidebar, {
    props: {
      timers: [],
      daemonSessions: [],
      ...props,
    },
  });
}

describe("ManageSidebar 定时任务展示", () => {
  test("默认显示定时任务页签，空态提示", () => {
    const wrapper = mountSidebar();
    expect(wrapper.find(".manage-sidebar").exists()).toBe(true);
    expect(wrapper.find(".manage-sidebar-empty").text()).toContain(
      "暂无定时任务",
    );
  });

  test("渲染定时任务列表（动作类型/状态/调度）", () => {
    const wrapper = mountSidebar({ timers: [timer()] });
    expect(wrapper.find(".manage-timer-item").exists()).toBe(true);
    expect(wrapper.find(".manage-timer-type").text()).toBe("调用能力");
    expect(wrapper.find(".manage-timer-status").text()).toBe("运行中");
    expect(wrapper.find(".manage-timer-schedule").text()).toContain("定时");
  });

  test("已取消任务显示取消状态", () => {
    const wrapper = mountSidebar({ timers: [timer({ cancelled: true })] });
    expect(wrapper.find(".manage-timer-status").text()).toBe("已取消");
    expect(wrapper.find(".manage-timer-status").classes()).toContain(
      "cancelled",
    );
  });

  test("动作类型未知时显示原始类型", () => {
    const wrapper = mountSidebar({
      timers: [timer({ metadata: { action: { type: "custom_action" } } })],
    });
    expect(wrapper.find(".manage-timer-type").text()).toBe("custom_action");
  });
});

describe("ManageSidebar daemon 能力展示", () => {
  test("无会话时提示暂无在线 daemon", async () => {
    const wrapper = mountSidebar();
    const tabs = wrapper.findAll(".manage-sidebar-tab");
    await tabs[1].trigger("click"); // 切到 daemon 能力页签
    expect(wrapper.find(".manage-sidebar-empty").text()).toContain(
      "暂无在线 daemon",
    );
  });

  test("切换页签到 daemon 能力，展示会话与能力", async () => {
    const wrapper = mountSidebar({ daemonSessions: [session()] });
    const tabs = wrapper.findAll(".manage-sidebar-tab");
    await tabs[1].trigger("click");
    expect(wrapper.find(".manage-session-name").text()).toBe("my-pc");
    // 展开会话后能力列表可见
    await wrapper.find(".manage-session-head").trigger("click");
    expect(wrapper.find(".manage-capability-name").text()).toBe("system.info");
  });

  test("展开会话后可查看能力详情（描述与参数）", async () => {
    const wrapper = mountSidebar({ daemonSessions: [session()] });
    const tabs = wrapper.findAll(".manage-sidebar-tab");
    await tabs[1].trigger("click");
    // 展开会话
    await wrapper.find(".manage-session-head").trigger("click");
    // 展开能力后可见描述与参数
    await wrapper.find(".manage-capability-head").trigger("click");
    expect(wrapper.find(".manage-capability-desc").text()).toContain(
      "查询系统信息",
    );
    expect(wrapper.find(".manage-capability-params-json").exists()).toBe(true);
  });
});

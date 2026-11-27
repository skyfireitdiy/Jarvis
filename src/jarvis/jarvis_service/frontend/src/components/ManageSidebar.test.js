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

function mountSidebar(props = {}) {
  return mount(ManageSidebar, {
    props: {
      timers: [],
      ...props,
    },
  });
}

describe("ManageSidebar 定时任务展示", () => {
  test("定时任务视图，空态提示", () => {
    const wrapper = mountSidebar();
    expect(wrapper.find(".manage-sidebar-title").text()).toBe("定时任务");
    expect(wrapper.find(".manage-sidebar-empty").text()).toContain(
      "暂无定时任务",
    );
  });

  test("定时任务视图不显示刷新按钮", () => {
    const wrapper = mountSidebar();
    expect(wrapper.find(".manage-sidebar-refresh").exists()).toBe(false);
  });

  test("渲染定时任务列表（动作类型/状态/调度）", () => {
    const wrapper = mountSidebar({ timers: [timer()] });
    expect(wrapper.find(".manage-timer-item").exists()).toBe(true);
    expect(wrapper.find(".manage-timer-type").text()).toBe("调用能力");
    expect(wrapper.find(".manage-timer-status").text()).toBe("运行中");
    expect(wrapper.find(".manage-timer-schedule").text()).toContain("定时");
  });

  test("已取消任务显示取消状态", () => {
    const wrapper = mountSidebar({
            timers: [timer({ cancelled: true })],
    });
    expect(wrapper.find(".manage-timer-status").text()).toBe("已取消");
    expect(wrapper.find(".manage-timer-status").classes()).toContain(
      "cancelled",
    );
  });

  test("cron 调度显示 cron 表达式", () => {
    const wrapper = mountSidebar({
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
            timers: [timer({ metadata: { action: { type: "custom_action" } } })],
    });
    expect(wrapper.find(".manage-timer-type").text()).toBe("custom_action");
  });

  test("run_shell_command 显示命令内容", () => {
    const wrapper = mountSidebar({
            timers: [
        timer({
          metadata: {
            action: {
              type: "run_shell_command",
              params: {
                command: "echo hello",
                working_dir: "/tmp",
                interpreter: "bash",
              },
            },
            schedule: { type: "interval", interval_seconds: 60 },
          },
        }),
      ],
    });
    expect(wrapper.find(".manage-timer-content").text()).toBe("echo hello");
    // 悬浮提示包含完整参数
    expect(wrapper.find(".manage-timer-content").attributes("title")).toContain(
      "working_dir",
    );
  });

  test("create_agent 显示 Agent 任务描述", () => {
    const wrapper = mountSidebar({
            timers: [
        timer({
          metadata: {
            action: {
              type: "create_agent",
              params: {
                agent_type: "code",
                working_dir: "/workspace",
                name: "my-agent",
                task: "实现登录功能",
              },
            },
            schedule: { type: "interval", interval_seconds: 3600 },
          },
        }),
      ],
    });
    expect(wrapper.find(".manage-timer-content").text()).toBe("实现登录功能");
  });

  test("capability_call 显示能力名", () => {
    const wrapper = mountSidebar({
            timers: [
        timer({
          metadata: {
            action: {
              type: "capability_call",
              params: { session_id: "sess-1", capability: "system.info" },
            },
            schedule: { type: "interval", interval_seconds: 30 },
          },
        }),
      ],
    });
    expect(wrapper.find(".manage-timer-content").text()).toBe("system.info");
  });

  test("无 action 参数时不渲染内容行", () => {
    const wrapper = mountSidebar({
            timers: [timer({ metadata: { action: { type: "custom_action" } } })],
    });
    expect(wrapper.find(".manage-timer-content").exists()).toBe(false);
  });
});

// CommandPalette 命令面板的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/CommandPalette.test.js   # 只跑本文件
//   npm run test:vitest                                    # 跑全部 vitest 用例
//
// 说明：CommandPalette 是受控组件——由 props.visible 控制显隐、props.ctx 提供
// 外部能力（Agent 列表 / 文件搜索结果 / 搜索回调），通过 emit 通知外部。测试
// 直接 mount 并传入 ctx 桩即可，无需 mock 网络。最近使用持久化到 localStorage，
// jsdom 可用，每个用例前清理。
import { describe, test, expect, beforeEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import CommandPalette from "./CommandPalette.vue";

// 构造一个命令动作对象（filterActions 依赖 id/label/group/icon/run 等字段）
function action(overrides = {}) {
  return {
    id: "cmd-1",
    label: "测试命令",
    icon: "🧪",
    group: "测试",
    run: () => {},
    ...overrides,
  };
}

// 构造 ctx 桩：默认提供空 Agent 列表与空文件结果，可覆盖
function makeCtx(overrides = {}) {
  return {
    agentList: [],
    openedAgentIds: new Set(),
    fileSearchResults: [],
    fileSearchLoading: false,
    fileSearchError: "",
    getAgentNodeLabel: () => "",
    getStatusClass: () => "running",
    searchWorkspaceFiles: () => {},
    clearWorkspaceFileSearch: () => {},
    ...overrides,
  };
}

// 默认挂载参数：visible=true + 一组动作 + ctx 桩
function mountPalette(props = {}) {
  return mount(CommandPalette, {
    props: {
      visible: true,
      actions: [action()],
      ctx: makeCtx(),
      title: "搜索命令…",
      initialQuery: "",
      ...props,
    },
  });
}

beforeEach(() => {
  localStorage.clear();
});

describe("前缀识别与占位符", () => {
  test("普通 query 为命令模式，placeholder 用 props.title", () => {
    const wrapper = mountPalette();
    expect(wrapper.find(".cmd-input").attributes("placeholder")).toBe(
      "搜索命令…",
    );
  });

  test("initialQuery='f>' 时进入文件模式，placeholder 为「搜索文件…」", () => {
    const wrapper = mountPalette({ initialQuery: "f>" });
    expect(wrapper.find(".cmd-input").attributes("placeholder")).toBe(
      "搜索文件…",
    );
  });

  test("initialQuery='a>' 时进入 Agent 模式，placeholder 为「搜索 Agent…」", () => {
    const wrapper = mountPalette({ initialQuery: "a>" });
    expect(wrapper.find(".cmd-input").attributes("placeholder")).toBe(
      "搜索 Agent…",
    );
  });
});

describe("文件模式渲染", () => {
  test("fileSearchResults 传入时渲染文件条目（label=name、meta=file_path）", () => {
    const wrapper = mountPalette({
      initialQuery: "f>",
      ctx: makeCtx({
        fileSearchResults: [
          { name: "setup.py", file_path: "/home/user/setup.py" },
        ],
      }),
    });
    const items = wrapper.findAll(".cmd-item");
    expect(items).toHaveLength(1);
    expect(items[0].find(".cmd-item-title").text()).toBe("setup.py");
    expect(items[0].find(".cmd-item-meta").text()).toBe("/home/user/setup.py");
  });

  test("fileSearchLoading 时空态为「搜索中…」", () => {
    const wrapper = mountPalette({
      initialQuery: "f>",
      ctx: makeCtx({ fileSearchLoading: true }),
    });
    expect(wrapper.find(".cmd-empty").text()).toBe("搜索中…");
  });

  test("fileSearchError 时空态为错误文案", () => {
    const wrapper = mountPalette({
      initialQuery: "f>",
      ctx: makeCtx({ fileSearchError: "搜索失败" }),
    });
    expect(wrapper.find(".cmd-empty").text()).toBe("搜索失败");
  });

  test("有查询词但无匹配时为空态「无匹配文件」", () => {
    const wrapper = mountPalette({
      initialQuery: "f>abc",
      ctx: makeCtx({ fileSearchResults: [] }),
    });
    expect(wrapper.find(".cmd-empty").text()).toBe("无匹配文件");
  });

  test("文件模式无查询词时空态为「输入文件名以搜索当前 Agent 工作区」", () => {
    const wrapper = mountPalette({
      initialQuery: "f>",
      ctx: makeCtx({ fileSearchResults: [] }),
    });
    expect(wrapper.find(".cmd-empty").text()).toBe(
      "输入文件名以搜索当前 Agent 工作区",
    );
  });
});

describe("Agent 模式渲染与排序", () => {
  const agents = [
    { agent_id: "a1", name: "运行中", status: "running" },
    { agent_id: "a2", name: "已停止", status: "stopped" },
    { agent_id: "a3", name: "已打开", status: "running" },
  ];

  // 注意：Agent 条目的 .cmd-item-title 内嵌 en 子元素（agent_id），text() 会拼接为 name+agent_id
  test("渲染 Agent 条目，label 取 name、en 取 agent_id", () => {
    const wrapper = mountPalette({
      initialQuery: "a>",
      ctx: makeCtx({ agentList: agents }),
    });
    const items = wrapper.findAll(".cmd-item");
    expect(items).toHaveLength(3);
    expect(items[0].find(".cmd-item-title").text()).toBe("运行中a1");
  });

  test("运行中排在已停止之前；opened 排在同运行态未打开之前", () => {
    const wrapper = mountPalette({
      initialQuery: "a>",
      ctx: makeCtx({
        agentList: agents,
        openedAgentIds: new Set(["a3"]),
      }),
    });
    // 排序规则：先按运行态（running 在前），再按 opened（打开在前）。
    // 期望顺序：a3(运行中已打开) / a1(运行中未打开) / a2(已停止)
    const titles = wrapper.findAll(".cmd-item-title").map((n) => n.text());
    expect(titles).toEqual(["已打开a3", "运行中a1", "已停止a2"]);
  });

  test("搜索词按 name/agent_id/nodeLabel 过滤", () => {
    const wrapper = mountPalette({
      initialQuery: "a>a2",
      ctx: makeCtx({
        agentList: agents,
        getAgentNodeLabel: (agent) =>
          agent.agent_id === "a1" ? "节点X" : "节点Y",
      }),
    });
    const titles = wrapper.findAll(".cmd-item-title").map((n) => n.text());
    // 仅 a2 命中（name 含 a2）
    expect(titles).toEqual(["已停止a2"]);
  });
});

describe("最近使用", () => {
  test("无搜索词时最近使用的命令置顶为「最近使用」分组", () => {
    localStorage.setItem(
      "jarvis_cmd_palette_recent",
      JSON.stringify(["cmd-recent"]),
    );
    const wrapper = mountPalette({
      actions: [
        action({ id: "cmd-recent", label: "最近命令" }),
        action({ id: "cmd-other", label: "其它命令" }),
      ],
    });
    const groupTitles = wrapper
      .findAll(".cmd-group-title")
      .map((n) => n.text());
    expect(groupTitles[0]).toBe("最近使用");
    // 最近使用分组里包含该命令，且常规列表不重复出现
    const firstGroupItems = wrapper
      .findAll(".cmd-group")[0]
      .findAll(".cmd-item-title")
      .map((n) => n.text());
    expect(firstGroupItems).toContain("最近命令");
    const allLabels = wrapper.findAll(".cmd-item-title").map((n) => n.text());
    expect(allLabels.filter((l) => l === "最近命令")).toHaveLength(1);
  });

  test("Agent 模式下不显示最近使用", () => {
    localStorage.setItem(
      "jarvis_cmd_palette_recent",
      JSON.stringify(["cmd-recent"]),
    );
    const wrapper = mountPalette({
      initialQuery: "a>",
      actions: [action({ id: "cmd-recent", label: "最近命令" })],
      ctx: makeCtx({ agentList: [] }),
    });
    expect(wrapper.find(".cmd-group-title").exists()).toBe(false);
    expect(wrapper.find(".cmd-empty").exists()).toBe(true);
  });

  test("文件模式下不显示最近使用", () => {
    localStorage.setItem(
      "jarvis_cmd_palette_recent",
      JSON.stringify(["cmd-recent"]),
    );
    const wrapper = mountPalette({
      initialQuery: "f>",
      actions: [action({ id: "cmd-recent", label: "最近命令" })],
      ctx: makeCtx({ fileSearchResults: [] }),
    });
    expect(wrapper.find(".cmd-group-title").exists()).toBe(false);
  });
});

describe("交互与 emit", () => {
  test("点击条目 emit('run', action, 'current')", async () => {
    const wrapper = mountPalette({ actions: [action({ id: "cmd-1" })] });
    await wrapper.find(".cmd-item").trigger("click");
    expect(wrapper.emitted("run")).toBeTruthy();
    expect(wrapper.emitted("run")[0][0].id).toBe("cmd-1");
    expect(wrapper.emitted("run")[0][1]).toBe("current");
  });

  test("Enter 触发当前选中条目的 run", async () => {
    const wrapper = mountPalette({ actions: [action({ id: "cmd-1" })] });
    await wrapper.find(".cmd-input").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("run")).toBeTruthy();
    expect(wrapper.emitted("run")[0][0].id).toBe("cmd-1");
  });

  test("ArrowDown 移动 activeIndex 并跳过 disabled 项", async () => {
    const wrapper = mountPalette({
      actions: [
        action({ id: "cmd-1", label: "一" }),
        action({ id: "cmd-2", label: "二", disabled: true }),
        action({ id: "cmd-3", label: "三" }),
      ],
    });
    // 初始 activeIndex=0（cmd-1）
    await wrapper.find(".cmd-input").trigger("keydown", { key: "ArrowDown" });
    // 跳过 disabled 的 cmd-2，落到 cmd-3
    const active = wrapper.findAll(".cmd-item.is-active");
    expect(active).toHaveLength(1);
    expect(active[0].find(".cmd-item-title").text()).toBe("三");
  });

  test("ArrowUp 移动 activeIndex", async () => {
    const wrapper = mountPalette({
      actions: [
        action({ id: "cmd-1", label: "一" }),
        action({ id: "cmd-2", label: "二" }),
      ],
    });
    // 先下移到最后，再上移回到第一个
    await wrapper.find(".cmd-input").trigger("keydown", { key: "ArrowDown" });
    await wrapper.find(".cmd-input").trigger("keydown", { key: "ArrowUp" });
    const active = wrapper.findAll(".cmd-item.is-active");
    expect(active[0].find(".cmd-item-title").text()).toBe("一");
  });

  test("Escape emit('update:visible', false) 与 'close'", async () => {
    const wrapper = mountPalette();
    await wrapper.find(".cmd-input").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("update:visible")).toBeTruthy();
    expect(wrapper.emitted("update:visible")[0]).toEqual([false]);
    expect(wrapper.emitted("close")).toBeTruthy();
  });

  test("disabled 条目点击不 emit run", async () => {
    const wrapper = mountPalette({
      actions: [action({ id: "cmd-1", disabled: true })],
    });
    await wrapper.find(".cmd-item").trigger("click");
    expect(wrapper.emitted("run")).toBeFalsy();
  });
});

describe("文件模式搜索回调", () => {
  test("文件模式输入变化时调用 ctx.searchWorkspaceFiles(query)", async () => {
    const searchWorkspaceFiles = vi.fn();
    const wrapper = mountPalette({
      initialQuery: "f>",
      ctx: makeCtx({ searchWorkspaceFiles }),
    });
    const input = wrapper.find(".cmd-input");
    await input.setValue("f>setup");
    expect(searchWorkspaceFiles).toHaveBeenCalledWith("setup");
  });

  test("离开文件模式时调用 ctx.clearWorkspaceFileSearch()", async () => {
    const clearWorkspaceFileSearch = vi.fn();
    const wrapper = mountPalette({
      initialQuery: "f>",
      ctx: makeCtx({ clearWorkspaceFileSearch }),
    });
    const input = wrapper.find(".cmd-input");
    await input.setValue("normal");
    expect(clearWorkspaceFileSearch).toHaveBeenCalled();
  });
});

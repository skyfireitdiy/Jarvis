// TerminalPanel 的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/TerminalPanel.test.js   # 只跑本文件
//   npm run test:vitest                                   # 跑全部 vitest 用例
//
// 说明：TerminalPanel 是纯展示型组件——由 props 驱动渲染、通过 emit 向外
// 通知交互。本测试重点覆盖「恢复会话」场景：只要 sessions 里有会话，
// 标签栏与内容区 hostEl 都应渲染并触发 setHostRef 事件，这是 App.vue 中
// setTerminalHostRef → initIndependentTerminal 初始化 xterm 的前置条件
// （修复「重新登录后只见标签不见 xterm」Bug 的回归保障）。
import { describe, test, expect } from "vitest";
import { mount } from "@vue/test-utils";
import TerminalPanel from "./TerminalPanel.vue";

// 构造一个会话
const session = (terminalId, overrides = {}) => ({
  terminal_id: terminalId,
  interpreter: "bash",
  access: "owner",
  ...overrides,
});

function mountPanel(props = {}) {
  return mount(TerminalPanel, {
    props: {
      visible: true,
      active: false,
      embedded: true,
      interaction: {},
      panelStyle: {},
      nodeOptions: [],
      selectedNodeId: "",
      socket: null,
      sessions: [],
      activeId: "",
      resizeDirections: [],
      formatNodeLabel: (n) => n.label || n.node_id,
      ...props,
    },
  });
}

describe("TerminalPanel 恢复会话渲染", () => {
  test("sessions 为空时显示空态，不触发 setHostRef", () => {
    const wrapper = mountPanel();
    expect(wrapper.find(".terminal-empty").exists()).toBe(true);
    expect(wrapper.emitted("setHostRef")).toBeUndefined();
  });

  test("sessions 有数据时渲染标签", () => {
    const wrapper = mountPanel({
      sessions: [session("t1"), session("t2")],
      activeId: "t1",
    });
    const tabs = wrapper.findAll(".terminal-tab");
    expect(tabs.length).toBe(2);
    expect(tabs[0].text()).toContain("bash");
  });

  test("sessions 有数据时内容区 hostEl 渲染并触发 setHostRef（el 非 null）", () => {
    const wrapper = mountPanel({
      sessions: [session("t1")],
      activeId: "t1",
    });
    // 内容区 host 容器渲染
    expect(wrapper.findAll(".terminal-host").length).toBe(1);
    // 触发 setHostRef，且 el 为真实 DOM 元素（非 null）
    const emitted = wrapper.emitted("setHostRef");
    expect(emitted).toBeTruthy();
    const [terminalId, el] = emitted[0];
    expect(terminalId).toBe("t1");
    expect(el).toBeTruthy();
    expect(el.nodeType).toBe(1); // ELEMENT_NODE
  });

  test("多个会话各触发一次 setHostRef，且 activeId 不匹配的会话 hostEl 也渲染（v-show 隐藏仍渲染）", () => {
    const wrapper = mountPanel({
      sessions: [session("t1"), session("t2")],
      activeId: "t1",
    });
    const emitted = wrapper.emitted("setHostRef");
    expect(emitted).toBeTruthy();
    const ids = emitted.map((e) => e[0]);
    expect(ids).toContain("t1");
    expect(ids).toContain("t2");
    // 内容区 host 容器数量 = 会话数（v-show 仅隐藏不销毁）
    expect(wrapper.findAll(".terminal-host").length).toBe(2);
  });

  test("owner 会话显示分享与关闭按钮，read 会话显示只读徽标", () => {
    const wrapper = mountPanel({
      sessions: [session("t1"), session("t2", { access: "read" })],
      activeId: "t1",
    });
    expect(wrapper.find(".terminal-tab-share").exists()).toBe(true);
    expect(wrapper.find(".terminal-tab-close").exists()).toBe(true);
    const readTab = wrapper.findAll(".terminal-tab")[1];
    expect(readTab.classes()).toContain("terminal-tab-readonly");
    expect(readTab.find(".terminal-tab-badge").exists()).toBe(true);
  });
});

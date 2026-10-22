// OrchestrationView 的组件单元测试（vitest + @vue/test-utils + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/components/OrchestrationView.test.js   # 只跑本文件
//   npm run test:vitest                                       # 跑全部 vitest 用例
//
// 说明：本组件是纯前端渲染（自绘 SVG DAG），不依赖后端接口；
// 审批报告预览通过 props.fetchFileContent 注入，测试中注入 mock 验证懒加载与渲染。
import { describe, test, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import OrchestrationView from "./OrchestrationView.vue";

// 构造一个处于「等待审批」状态的流水线（full 模式审批浮层显示的前提）
function gateBlockedPipeline(overrides = {}) {
  const stages = new Map([
    ["recon", { stage: "recon", name: "侦察", status: "completed" }],
    ["build", { stage: "build", name: "构建", status: "completed" }],
    ["review", { stage: "review", name: "评审", status: "completed" }],
  ]);
  return {
    pipelineId: "pipe-1",
    orchestrationFile: "dark_factory.yaml",
    workingDir: "/work/demo",
    approvalPath: ".df/approval.md",
    gateStage: "review",
    finalStatus: "gate_blocked",
    startedAt: Date.now() - 60_000,
    stageOrder: ["recon", "build", "review"],
    stages,
    approvals: [{ action: "pending", who: "system", ts: Date.now() }],
    ...overrides,
  };
}

const baseProps = {
  pipelines: [gateBlockedPipeline()],
  activeId: "pipe-1",
  mode: "full",
  fetchFileContent: vi.fn(async () => "# 审批报告\n\n同意放行。"),
};

describe("OrchestrationView 审批报告预览", () => {
  beforeEach(() => {
    baseProps.fetchFileContent.mockClear();
  });

  test("gate_blocked 流水线在 full 模式显示审批浮层与预览按钮", () => {
    const wrapper = mount(OrchestrationView, { props: baseProps });
    expect(wrapper.find(".orch-approval").exists()).toBe(true);
    const btn = wrapper.find(".orch-btn.is-preview");
    expect(btn.exists()).toBe(true);
    expect(btn.text()).toContain("预览审批报告");
    // 未点击前不发起读取（懒加载）
    expect(baseProps.fetchFileContent).not.toHaveBeenCalled();
  });

  test("点击预览按钮懒加载并渲染 markdown 审批报告", async () => {
    const wrapper = mount(OrchestrationView, { props: baseProps });
    await wrapper.find(".orch-btn.is-preview").trigger("click");
    await flushPromises();
    // 按 workingDir + approvalPath 拼接绝对路径读取
    expect(baseProps.fetchFileContent).toHaveBeenCalledWith("/work/demo/.df/approval.md");
    const body = wrapper.find(".orch-approval-report-body");
    expect(body.exists()).toBe(true);
    expect(body.html()).toContain("<h1>审批报告</h1>");
    // 再次点击收起
    await wrapper.find(".orch-btn.is-preview").trigger("click");
    expect(wrapper.find(".orch-approval-report").exists()).toBe(false);
  });

  test("读取失败时展示错误信息", async () => {
    baseProps.fetchFileContent.mockRejectedValueOnce(new Error("文件不存在"));
    const wrapper = mount(OrchestrationView, { props: baseProps });
    await wrapper.find(".orch-btn.is-preview").trigger("click");
    await flushPromises();
    const err = wrapper.find(".orch-approval-report-state.is-err");
    expect(err.exists()).toBe(true);
    expect(err.text()).toContain("文件不存在");
  });

  test("未注入 fetchFileContent 时提示不支持预览", async () => {
    const wrapper = mount(OrchestrationView, {
      props: { ...baseProps, fetchFileContent: null },
    });
    await wrapper.find(".orch-btn.is-preview").trigger("click");
    await flushPromises();
    const err = wrapper.find(".orch-approval-report-state.is-err");
    expect(err.exists()).toBe(true);
    expect(err.text()).toContain("不支持预览审批报告");
  });

  test("approvalPath 为绝对路径时去前导斜杠拼接", async () => {
    const wrapper = mount(OrchestrationView, {
      props: {
        ...baseProps,
        pipelines: [gateBlockedPipeline({ approvalPath: "/.df/approval.md" })],
      },
    });
    await wrapper.find(".orch-btn.is-preview").trigger("click");
    await flushPromises();
    expect(baseProps.fetchFileContent).toHaveBeenCalledWith("/work/demo/.df/approval.md");
  });
});

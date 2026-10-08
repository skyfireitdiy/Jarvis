// pipelineStore 的单元测试（零依赖，用 node 内置 test runner）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/stores/pipelineStore.test.mjs   # 只跑本文件
//   node --test                                     # 自动发现全部 *.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { PipelineStore, STAGE_STATUS } from "./pipelineStore.js";

function startEvent(pid, stages) {
  return {
    pipeline_id: pid,
    type: "pipeline_start",
    orchestration_file: "/x/pipeline.yaml",
    nodes: stages.map((s) => ({
      stage: s.stage,
      agent: s.agent || "a",
      depends_on: s.depends_on || [],
      input: [],
      output: s.output || "",
      gate: !!s.gate,
      when: null,
      retry: 0,
      on_error: "abort",
    })),
  };
}

test("pipeline_start：建立流程并初始化所有 stage 为 pending", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }, { stage: "s2", depends_on: ["s1"] }]));
  const st = store.getPipeline("p1");
  assert.ok(st);
  assert.equal(st.stages.get("s1").status, STAGE_STATUS.PENDING);
  assert.equal(st.stages.get("s2").status, STAGE_STATUS.PENDING);
  assert.deepEqual(st.stages.get("s2").dependsOn, ["s1"]);
});

test("pipeline_agents：回填 agentId", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  store.applyEvent({ pipeline_id: "p1", type: "pipeline_agents", agent_map: { s1: "agent-123" } });
  assert.equal(store.getPipeline("p1").stages.get("s1").agentId, "agent-123");
});

test("stage_update：更新状态与错误信息", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  store.applyEvent({ pipeline_id: "p1", type: "stage_update", stage: "s1", status: "running" });
  assert.equal(store.getPipeline("p1").stages.get("s1").status, STAGE_STATUS.RUNNING);
  store.applyEvent({
    pipeline_id: "p1",
    type: "stage_update",
    stage: "s1",
    status: "failed",
    error: "boom",
  });
  const node = store.getPipeline("p1").stages.get("s1");
  assert.equal(node.status, STAGE_STATUS.FAILED);
  assert.equal(node.error, "boom");
});

test("stage_update retry：状态归为 running 并记录重试次数", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  store.applyEvent({
    pipeline_id: "p1",
    type: "stage_update",
    stage: "s1",
    status: "retry",
    retry_count: 2,
  });
  const node = store.getPipeline("p1").stages.get("s1");
  assert.equal(node.status, STAGE_STATUS.RUNNING);
  assert.equal(node.retryCount, 2);
});

test("pipeline_done：置终态并记录 success/finalStatus", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  store.applyEvent({
    pipeline_id: "p1",
    type: "pipeline_done",
    success: false,
    final_status: "failed",
  });
  const st = store.getPipeline("p1");
  assert.equal(st.success, false);
  assert.equal(st.finalStatus, "failed");
  assert.ok(st.finishedAt);
});

test("幂等：重复 stage_update 覆盖不追加节点", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  store.applyEvent({ pipeline_id: "p1", type: "stage_update", stage: "s1", status: "running" });
  store.applyEvent({ pipeline_id: "p1", type: "stage_update", stage: "s1", status: "running" });
  assert.equal(store.getPipeline("p1").stages.size, 1);
});

test("未知 pipeline_id 的 stage_update 被忽略", () => {
  const store = new PipelineStore();
  assert.equal(store.applyEvent({ pipeline_id: "nope", type: "stage_update", stage: "s1" }), null);
  assert.equal(store.pipelines.size, 0);
});

test("listPipelines：按 startedAt 倒序", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  store.getPipeline("p1").startedAt = 1000;
  store.applyEvent(startEvent("p2", [{ stage: "s1" }]));
  store.getPipeline("p2").startedAt = 2000;
  assert.deepEqual(
    store.listPipelines().map((s) => s.pipelineId),
    ["p2", "p1"],
  );
});

test("pruneFinished：仅保留最近 N 条已结束流程，运行中不裁剪", () => {
  const store = new PipelineStore(2);
  // 3 条已结束
  for (let i = 0; i < 3; i++) {
    store.applyEvent(startEvent(`done${i}`, [{ stage: "s1" }]));
    store.getPipeline(`done${i}`).startedAt = i;
    store.applyEvent({ pipeline_id: `done${i}`, type: "pipeline_done", success: true });
  }
  // 1 条运行中（较早开始，不应被裁剪）
  store.applyEvent(startEvent("live", [{ stage: "s1" }]));
  store.getPipeline("live").startedAt = -1;

  store.pruneFinished();
  const ids = store.listPipelines().map((s) => s.pipelineId);
  // 已结束保留最近 2 条：done2、done1；done0 被裁剪
  assert.ok(ids.includes("done2"));
  assert.ok(ids.includes("done1"));
  assert.ok(!ids.includes("done0"));
  assert.ok(ids.includes("live"));
});

test("非对象/无 pipeline_id 事件被忽略", () => {
  const store = new PipelineStore();
  assert.equal(store.applyEvent(null), null);
  assert.equal(store.applyEvent("x"), null);
  assert.equal(store.applyEvent({ type: "pipeline_start" }), null);
});

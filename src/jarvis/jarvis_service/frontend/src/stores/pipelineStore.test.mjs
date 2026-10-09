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
  store.applyEvent(
    startEvent("p1", [{ stage: "s1" }, { stage: "s2", depends_on: ["s1"] }]),
  );
  const st = store.getPipeline("p1");
  assert.ok(st);
  assert.equal(st.stages.get("s1").status, STAGE_STATUS.PENDING);
  assert.equal(st.stages.get("s2").status, STAGE_STATUS.PENDING);
  assert.deepEqual(st.stages.get("s2").dependsOn, ["s1"]);
});

test("pipeline_agents：回填 agentId", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  store.applyEvent({
    pipeline_id: "p1",
    type: "pipeline_agents",
    agent_map: { s1: "agent-123" },
  });
  assert.equal(store.getPipeline("p1").stages.get("s1").agentId, "agent-123");
});

test("stage_update：更新状态与错误信息", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  store.applyEvent({
    pipeline_id: "p1",
    type: "stage_update",
    stage: "s1",
    status: "running",
  });
  assert.equal(
    store.getPipeline("p1").stages.get("s1").status,
    STAGE_STATUS.RUNNING,
  );
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
  store.applyEvent({
    pipeline_id: "p1",
    type: "stage_update",
    stage: "s1",
    status: "running",
  });
  store.applyEvent({
    pipeline_id: "p1",
    type: "stage_update",
    stage: "s1",
    status: "running",
  });
  assert.equal(store.getPipeline("p1").stages.size, 1);
});

test("pipeline_approval：追加审批日志到 approvals", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "gate1", gate: true }]));
  // 先广播 pending（等待审批）
  store.applyEvent({
    pipeline_id: "p1",
    type: "pipeline_approval",
    action: "pending",
    gate_stage: "gate1",
    approval_path: "/x/report.md",
    ts: 1000,
  });
  // 再广播一条审批决定（放行）
  store.applyEvent({
    pipeline_id: "p1",
    type: "pipeline_approval",
    action: "approve",
    approver: "admin",
    note: "确认无误",
    gate_stage: "gate1",
    approval_path: "/x/report.md",
    ts: 2000,
  });
  const st = store.getPipeline("p1");
  assert.ok(Array.isArray(st.approvals), "approvals 应为数组");
  assert.equal(st.approvals.length, 2);
  assert.equal(st.approvals[0].action, "pending");
  assert.equal(st.approvals[0].gateStage, "gate1");
  assert.equal(st.approvals[1].action, "approve");
  assert.equal(st.approvals[1].approver, "admin");
  assert.equal(st.approvals[1].note, "确认无误");
  assert.equal(st.approvals[1].ts, 2000);
});

test("pipeline_start / addPreview 初始化 approvals 为空数组", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  assert.deepEqual(store.getPipeline("p1").approvals, []);
  const st = store.addPreview(
    "preview_x",
    [
      {
        stage: "s1",
        agent: "a",
        depends_on: [],
        input: [],
        output: "",
        gate: false,
        when: null,
        retry: 0,
        on_error: "abort",
      },
    ],
    "/x/p.yaml",
  );
  assert.deepEqual(st.approvals, []);
});

test("pipeline_done：旧数据无 approvals 时兜底为空数组", () => {
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  // 模拟持久化恢复的旧数据：无 approvals 字段
  delete store.getPipeline("p1").approvals;
  store.applyEvent({
    pipeline_id: "p1",
    type: "pipeline_done",
    success: true,
    final_status: "completed",
  });
  assert.deepEqual(
    store.getPipeline("p1").approvals,
    [],
    "pipeline_done 应兜底初始化 approvals",
  );
});

test("未知 pipeline_id 的 stage_update 被忽略", () => {
  const store = new PipelineStore();
  assert.equal(
    store.applyEvent({
      pipeline_id: "nope",
      type: "stage_update",
      stage: "s1",
    }),
    null,
  );
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
    store.applyEvent({
      pipeline_id: `done${i}`,
      type: "pipeline_done",
      success: true,
    });
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

// ---- localStorage 持久化（storageKey 非空时开启）----
function installLocalStorageMock() {
  const backing = new Map();
  const storage = {
    getItem: (k) => (backing.has(k) ? backing.get(k) : null),
    setItem: (k, v) => backing.set(k, String(v)),
    removeItem: (k) => backing.delete(k),
    clear: () => backing.clear(),
    _backing: backing,
  };
  globalThis.localStorage = storage;
  return storage;
}

test("开启 storageKey 后 applyEvent 自动持久化，新实例可恢复", () => {
  const storage = installLocalStorageMock();
  const store = new PipelineStore(20, "orchestration");
  store.applyEvent(
    startEvent("p1", [{ stage: "s1" }, { stage: "s2", depends_on: ["s1"] }]),
  );
  store.applyEvent({
    pipeline_id: "p1",
    type: "stage_update",
    stage: "s1",
    status: "completed",
    artifact: "out.md",
  });
  store.applyEvent({
    pipeline_id: "p1",
    type: "pipeline_done",
    success: true,
    final_status: "completed",
  });

  // 持久化键存在且内容非空
  const key = "jarvis_pipeline_store_orchestration";
  assert.ok(storage.getItem(key), "应写入 localStorage");

  // 新实例（模拟刷新）能从 localStorage 恢复
  const restored = new PipelineStore(20, "orchestration");
  const st = restored.getPipeline("p1");
  assert.ok(st, "刷新后应恢复流程");
  assert.equal(st.stages.get("s1").status, STAGE_STATUS.COMPLETED);
  assert.equal(st.stages.get("s1").artifact, "out.md");
  assert.equal(st.finalStatus, "completed");
});

test("不传 storageKey 时保持纯内存、不碰 localStorage", () => {
  const storage = installLocalStorageMock();
  const store = new PipelineStore();
  store.applyEvent(startEvent("p1", [{ stage: "s1" }]));
  assert.equal(
    storage.getItem("jarvis_pipeline_store_"),
    null,
    "不应写入 localStorage",
  );
});

test("addPreview：以静态 preview 态加入 DAG，所有 stage 为 pending 且不运行", () => {
  const store = new PipelineStore();
  const nodes = [
    {
      stage: "s1",
      agent: "a",
      depends_on: [],
      input: [],
      output: "",
      gate: false,
      when: null,
      retry: 0,
      on_error: "abort",
    },
    {
      stage: "s2",
      agent: "b",
      depends_on: ["s1"],
      input: [],
      output: "",
      gate: false,
      when: null,
      retry: 0,
      on_error: "abort",
    },
  ];
  const st = store.addPreview("preview_x", nodes, "/x/pipeline.yaml");
  assert.ok(st, "应返回新 state");
  assert.equal(st.finalStatus, "preview");
  assert.ok(st.finishedAt, "预览态应视为已结束，避免跳动动画");
  assert.equal(st.success, true);
  assert.equal(st.orchestrationFile, "/x/pipeline.yaml");
  assert.equal(st.stages.get("s1").status, STAGE_STATUS.PENDING);
  assert.equal(st.stages.get("s2").status, STAGE_STATUS.PENDING);
  assert.deepEqual(st.stageOrder, ["s1", "s2"]);
  assert.equal(store.getPipeline("preview_x"), st);
});

test("addPreview：缺 pipelineId 或 nodes 非法时返回 null", () => {
  const store = new PipelineStore();
  assert.equal(store.addPreview("", []), null);
  assert.equal(store.addPreview("p", null), null);
  assert.equal(store.addPreview("p", "not-array"), null);
});

test("removePipeline：删除单个流程并同步持久化", () => {
  installLocalStorageMock();
  const store = new PipelineStore(20, "del");
  store.addPreview(
    "preview_a",
    [
      {
        stage: "s1",
        agent: "a",
        depends_on: [],
        input: [],
        output: "",
        gate: false,
        when: null,
        retry: 0,
        on_error: "abort",
      },
    ],
    "/x/a.yaml",
  );
  store.addPreview(
    "preview_b",
    [
      {
        stage: "s1",
        agent: "b",
        depends_on: [],
        input: [],
        output: "",
        gate: false,
        when: null,
        retry: 0,
        on_error: "abort",
      },
    ],
    "/x/b.yaml",
  );
  assert.equal(store.listPipelines().length, 2);

  // 删除存在的项
  assert.equal(store.removePipeline("preview_a"), true);
  assert.equal(store.listPipelines().length, 1);
  assert.equal(store.getPipeline("preview_a"), null);
  assert.ok(store.getPipeline("preview_b"), "未删除的项应保留");

  // 删除不存在的项返回 false
  assert.equal(store.removePipeline("preview_a"), false);

  // 持久化已同步：新实例只恢复剩余项
  const restored = new PipelineStore(20, "del");
  assert.equal(restored.listPipelines().length, 1);
  assert.equal(
    restored.getPipeline("preview_b").orchestrationFile,
    "/x/b.yaml",
  );
});

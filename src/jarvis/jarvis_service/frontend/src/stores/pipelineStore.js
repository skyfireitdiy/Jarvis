// 流水线进度状态仓库（纯 JS，无 Vue / 第三方依赖）。
//
// 消费后端 pipeline_event 广播（见 pipeline_events.py / web_gateway 桥接线程）：
//   { type: "pipeline_event", payload: <event> }
// event 形如：
//   { pipeline_id, type: "pipeline_start", nodes: [{stage,agent,depends_on,...}], ... }
//   { pipeline_id, type: "pipeline_agents", agent_map: {stage: agent_id} }
//   { pipeline_id, type: "stage_update", stage, status, ... }
//   { pipeline_id, type: "pipeline_done", success, final_status, ... }
//
// 设计要点：
// - 幂等：同一 stage 的重复事件按 status 覆盖，不追加节点。
// - 有界：仅保留最近 N 条「已结束」流程（pruneFinished），运行中的不裁剪。

export const STAGE_STATUS = {
  PENDING: "pending",
  RUNNING: "running",
  COMPLETED: "completed",
  FAILED: "failed",
  SKIPPED: "skipped",
  RETRY: "retry",
};

const TERMINAL_STATUSES = new Set(["completed", "failed", "aborted", "gate_blocked"]);

function emptyStage(node) {
  return {
    stage: node.stage,
    agent: node.agent || "",
    agentId: "",
    dependsOn: Array.isArray(node.depends_on) ? [...node.depends_on] : [],
    input: Array.isArray(node.input) ? [...node.input] : [],
    output: node.output || "",
    gate: !!node.gate,
    when: node.when || null,
    retry: node.retry || 0,
    onError: node.on_error || "abort",
    status: STAGE_STATUS.PENDING,
    error: "",
    artifact: "",
    retryCount: 0,
  };
}

// localStorage 键前缀：持久化键 = `${PIPELINE_STORE_KEY_PREFIX}${storageKey}`
const PIPELINE_STORE_KEY_PREFIX = "jarvis_pipeline_store_";

export class PipelineStore {
  // storageKey 非空时开启 localStorage 持久化：applyEvent 后自动保存快照，
  // 构造时自动恢复，使刷新页面后仍能看到已运行的编排（事件广播是纯内存、不落盘）。
  // 单元测试不传 storageKey，保持纯内存、不碰 localStorage。
  constructor(maxFinished = 20, storageKey = "") {
    this.maxFinished = maxFinished;
    this.pipelines = new Map();
    this.storageKey = storageKey;
    if (storageKey) {
      this._restoreFromStorage();
    }
  }

  _storageKey() {
    return PIPELINE_STORE_KEY_PREFIX + this.storageKey;
  }

  // 把当前状态序列化为可 JSON 化的普通对象（Map → 数组）。
  _serialize() {
    return [...this.pipelines.values()].map((s) => ({
      ...s,
      stages: [...s.stages.entries()].map(([stage, node]) => ({ stage, node })),
    }));
  }

  // 从 localStorage 恢复历史流程（构造时调用）。失败/无数据时静默。
  _restoreFromStorage() {
    try {
      const raw = localStorage.getItem(this._storageKey());
      if (!raw) return;
      const list = JSON.parse(raw);
      if (!Array.isArray(list)) return;
      for (const s of list) {
        if (!s || !s.pipelineId || !Array.isArray(s.stages)) continue;
        const stages = new Map();
        for (const { stage, node } of s.stages) {
          if (stage) stages.set(stage, node);
        }
        this.pipelines.set(s.pipelineId, { ...s, stages });
      }
    } catch (err) {
      // 隐私模式/损坏数据时忽略，保持空内存态
      console.warn("[PIPELINE] Failed to restore pipeline store:", err);
    }
  }

  // 把当前状态写入 localStorage（开启持久化时）。
  _persist() {
    if (!this.storageKey) return;
    try {
      localStorage.setItem(this._storageKey(), JSON.stringify(this._serialize()));
    } catch (err) {
      // 隐私模式/配额满时忽略，不影响内存态
      console.warn("[PIPELINE] Failed to persist pipeline store:", err);
    }
  }

  // 应用一条事件；未知类型/无 pipeline_id 的事件被忽略。
  applyEvent(event) {
    if (!event || typeof event !== "object") return null;
    const pid = event.pipeline_id;
    if (!pid) return null;
    const type = event.type;

    if (type === "pipeline_start") {
      const stages = new Map();
      for (const n of event.nodes || []) {
        stages.set(n.stage, emptyStage(n));
      }
      const state = {
        pipelineId: pid,
        orchestrationFile: event.orchestration_file || "",
        specFile: event.spec_file || "",
        workingDir: event.working_dir || "",
        maxWorkers: event.max_workers || 0,
        approve: !!event.approve,
        defaultOnError: event.default_on_error || "abort",
        stages,
        stageOrder: (event.nodes || []).map((n) => n.stage),
        startedAt: Date.now(),
        finishedAt: null,
        success: null,
        finalStatus: "running",
        gateStage: "",
        approvalPath: "",
      };
      this.pipelines.set(pid, state);
      this._persist();
      return state;
    }

    const state = this.pipelines.get(pid);
    if (!state) return null;

    if (type === "pipeline_agents") {
      const map = event.agent_map || {};
      for (const [stage, agentId] of Object.entries(map)) {
        const node = state.stages.get(stage);
        if (node) node.agentId = agentId;
      }
      this._persist();
      return state;
    }

    if (type === "stage_update") {
      const node = state.stages.get(event.stage);
      if (!node) return state;
      if (event.status === "retry") {
        node.status = STAGE_STATUS.RUNNING;
        node.retryCount = event.retry_count || node.retryCount;
      } else {
        node.status = event.status || node.status;
      }
      if (event.error !== undefined) node.error = event.error || "";
      if (event.artifact !== undefined) node.artifact = event.artifact || "";
      if (event.agent_id) node.agentId = event.agent_id;
      this._persist();
      return state;
    }

    if (type === "pipeline_done") {
      state.finishedAt = Date.now();
      state.success = !!event.success;
      state.finalStatus = event.final_status || (event.success ? "completed" : "failed");
      state.gateStage = event.gate_stage || "";
      state.approvalPath = event.approval_path || "";
      this.pruneFinished();
      this._persist();
      return state;
    }

    return state;
  }

  getPipeline(pid) {
    return this.pipelines.get(pid) || null;
  }

  // 按开始时间倒序返回全部流程（最新在前）。
  listPipelines() {
    return [...this.pipelines.values()].sort((a, b) => b.startedAt - a.startedAt);
  }

  isFinished(state) {
    return state && state.finishedAt != null;
  }

  // 仅裁剪「已结束」流程，保留最近 maxFinished 条；运行中的永不裁剪。
  pruneFinished() {
    const finished = this.listPipelines().filter((s) => this.isFinished(s));
    if (finished.length <= this.maxFinished) return;
    const toRemove = finished.slice(this.maxFinished);
    for (const s of toRemove) this.pipelines.delete(s.pipelineId);
  }

  clear() {
    this.pipelines.clear();
  }
}

export function isTerminalStatus(status) {
  return TERMINAL_STATUSES.has(status);
}

// 网络拓扑数据模型与布局（纯 JS，无 Vue / 第三方依赖）
// nodes: [{ node_id, status, ... }]  agents: [{ agent_id, name, node_id, status, ... }]

export const NODE_STATE = {
  ONLINE: "online",
  OFFLINE: "offline",
  UNKNOWN: "unknown",
};

export const AGENT_STATE = {
  RUNNING: "running",
  WAITING: "waiting",
  IDLE: "idle",
  STOPPED: "stopped",
};

const ONLINE_ALIASES = new Set([
  "online",
  "running",
  "ready",
  "connected",
  "up",
]);

export function normalizeNodeStatus(raw) {
  const value = String(raw || "")
    .trim()
    .toLowerCase();
  if (!value) return NODE_STATE.UNKNOWN;
  if (ONLINE_ALIASES.has(value)) return NODE_STATE.ONLINE;
  if (
    value === "offline" ||
    value === "stopped" ||
    value === "down" ||
    value === "disconnected"
  ) {
    return NODE_STATE.OFFLINE;
  }
  return NODE_STATE.UNKNOWN;
}

export function normalizeAgentStatus(rawStatusClass) {
  const value = String(rawStatusClass || "")
    .trim()
    .toLowerCase();
  if (!value) return AGENT_STATE.IDLE;
  if (value === "stopped") return AGENT_STATE.STOPPED;
  if (value.startsWith("waiting")) return AGENT_STATE.WAITING;
  if (value === "running") return AGENT_STATE.RUNNING;
  return AGENT_STATE.IDLE;
}

// 将节点与 agent 组装成以 master 为中心的拓扑模型
export function buildTopology(nodes, agents, getStatusClass) {
  const nodeList = Array.isArray(nodes) ? nodes : [];
  const agentList = Array.isArray(agents) ? agents : [];
  const resolveStatusClass =
    typeof getStatusClass === "function" ? getStatusClass : () => "running";

  const nodeMap = new Map();
  const registerNode = (id, raw) => {
    const key = String(id || "").trim() || "master";
    if (!nodeMap.has(key)) {
      nodeMap.set(key, {
        id: key,
        label: key,
        state: normalizeNodeStatus(raw && raw.status),
        isCenter: key === "master",
        agents: [],
      });
    }
    return nodeMap.get(key);
  };

  // 先注册所有显式节点，确保 master 存在
  nodeList.forEach((node) => registerNode(node && node.node_id, node));
  if (!nodeMap.has("master")) {
    nodeMap.set("master", {
      id: "master",
      label: "master",
      state: NODE_STATE.ONLINE,
      isCenter: true,
      agents: [],
    });
  }

  // agent 按 node_id 归位
  agentList.forEach((agent) => {
    const nodeId = String((agent && agent.node_id) || "").trim() || "master";
    const node = registerNode(
      nodeId,
      nodeMap.get(nodeId) || { status: "unknown" },
    );
    const state = normalizeAgentStatus(resolveStatusClass(agent));
    node.agents.push({
      id: String((agent && agent.agent_id) || "").trim(),
      name: String(
        (agent && agent.name) || (agent && agent.agent_id) || "",
      ).trim(),
      type:
        (agent && agent.agent_type) === "code_agent" ? "code_agent" : "agent",
      state,
      // 已停止的 agent 不绘制到拓扑图上，仅作数据显示
      stopped: state === AGENT_STATE.STOPPED,
    });
  });

  const center = nodeMap.get("master");
  const rest = [];
  nodeMap.forEach((node) => {
    if (!node.isCenter) rest.push(node);
  });
  const orderedNodes = [...rest];

  // 每个节点上「参与绘制」的 agent（过滤已停止）；center 同样处理
  const pickDrawAgents = (node) => node.agents.filter((a) => !a.stopped);
  orderedNodes.forEach((node) => {
    node.drawAgents = pickDrawAgents(node);
  });
  center.drawAgents = pickDrawAgents(center);

  const links = orderedNodes.map((node) => ({
    source: "master",
    target: node.id,
  }));

  let waiting = 0;
  let running = 0;
  let stopped = 0;
  let idle = 0;
  let online = 0;
  orderedNodes.forEach((node) => {
    if (node.state === NODE_STATE.ONLINE) online++;
  });
  if (center.state === NODE_STATE.ONLINE) online++;
  let agentTotal = 0;
  let agentActive = 0;
  nodeMap.forEach((node) => {
    agentTotal += node.agents.length;
    node.agents.forEach((a) => {
      if (!a.stopped) agentActive++;
      if (a.state === AGENT_STATE.WAITING) waiting++;
      else if (a.state === AGENT_STATE.RUNNING) running++;
      else if (a.state === AGENT_STATE.STOPPED) stopped++;
      else idle++;
    });
  });

  return {
    center,
    nodes: orderedNodes,
    links,
    counts: {
      nodes: nodeMap.size,
      online,
      // agents 为全量（含已停止，用于数据显示）
      agents: agentTotal,
      // activeAgents 为参与绘制的 agent 数（不含已停止）
      activeAgents: agentActive,
      waiting,
      // agent 各状态计数（waiting 已在上面累计）
      running,
      stopped,
      idle,
    },
  };
}

// 环形布局：master 居中，其余节点均匀分布圆周（首个在正上方）
export function layoutTopology(model, width, height) {
  const w = Number(width) || 240;
  const h = Number(height) || 240;
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) * 0.34;
  const nodes = (model && model.nodes) || [];
  const count = nodes.length;
  const positioned = nodes.map((node, index) => {
    if (count === 0) return { id: node.id, x: cx, y: cy, angle: -Math.PI / 2 };
    // 从正上方（-90°）开始顺时针均匀分布
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / count;
    return {
      id: node.id,
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
      // 记录方位角：agent 布局据此把 agent 排到「背向中心」的外侧
      angle,
    };
  });
  return {
    center: { x: cx, y: cy },
    nodes: positioned,
    radius,
  };
}

// 将「参与绘制」的 agent 布局到各自节点周围：
// - 中心节点：agent 环绕一周
// - 其余节点：agent 只分布在「背向中心」的外侧扇形内，避免朝内侧的 agent
//   与相邻节点（及其 agent）重叠
// 每个 agent 附带标签坐标：标签沿径向朝外摆放，避免压住节点本体文字
// options.ring：子节点 agent 环绕半径；options.centerRing：中心 agent 环绕半径；
// options.labelGap：标签相对 agent 图标外沿额外外移的距离；
// options.agentRadius：agent 图标半径（标签在此基础上再外移 labelGap，避免与图标/天线重叠）；
// options.minGap：相邻 agent 圆心最小间距（不足时自动放大环半径）；
// options.canvas：{ width, height }，用于限制环半径不溢出画布；
// options.edgePad：环外沿到画布边缘的最小预留（agent 半径 + 标签）
export function layoutAgents(model, nodeLayout, options = {}) {
  const ring = Number(options.ring) || 34;
  const centerRing = Number(options.centerRing) || ring;
  const labelGap = Number(options.labelGap) || 12;
  const agentRadius = Number(options.agentRadius) || 0;
  const minGap = Number(options.minGap) || 26;
  const canvas = options.canvas || null;
  const edgePad = Number(options.edgePad) || 0;
  const placed = [];

  // 节点处环半径上限：不超出画布（各方向取最小余量）
  const ringLimitAt = (pos) => {
    if (!canvas) return Infinity;
    const w = Number(canvas.width) || 0;
    const h = Number(canvas.height) || 0;
    return Math.max(0, Math.min(pos.x, w - pos.x, pos.y, h - pos.y) - edgePad);
  };

  if (!model || !nodeLayout) return { agents: placed };

  const push = (agent, nodeId, pos, r, angle) => {
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    // 标签从「agent 图标外沿」再向外偏移 labelGap，避免压住图标与天线
    const labelDist = r + agentRadius + labelGap;
    placed.push({
      id: agent.id,
      name: agent.name,
      type: agent.type || "agent",
      state: agent.state,
      nodeId,
      x: pos.x + r * cos,
      y: pos.y + r * sin,
      labelX: pos.x + labelDist * cos,
      labelY: pos.y + labelDist * sin,
      labelAnchor: cos > 0.35 ? "start" : cos < -0.35 ? "end" : "middle",
      labelBaseline: sin > 0.4 ? "hanging" : sin < -0.4 ? "auto" : "middle",
    });
  };

  // 中心节点：agent 环绕一周
  const centerPos = nodeLayout.center;
  if (model.center && centerPos) {
    const list = model.center.drawAgents || [];
    const total = list.length;
    list.forEach((agent, i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / total;
      push(agent, model.center.id, centerPos, centerRing, angle);
    });
  }

  // 其余节点：agent 分布在背向中心的扇形内
  const nodeCount = (model.nodes || []).length || 1;
  // 扇形半角：节点越多，扇形越窄，避免相邻节点的扇形互相侵入
  const spreadDeg = Math.min(80, Math.max(38, 180 / nodeCount - 10));
  const spread = (spreadDeg * Math.PI) / 180;
  const posMap = new Map((nodeLayout.nodes || []).map((p) => [p.id, p]));
  (model.nodes || []).forEach((node) => {
    const pos = posMap.get(node.id);
    const list = node.drawAgents || [];
    if (!pos || list.length === 0) return;
    // 朝外方向：节点相对中心的方位角
    const baseAngle = Number.isFinite(pos.angle) ? pos.angle : -Math.PI / 2;
    const total = list.length;
    const step = total > 1 ? (spread * 2) / (total - 1) : 0;
    // agent 多时弧距不足，自动放大环半径（保证相邻 agent 圆心间距 >= minGap）
    // 但不超过该节点到画布边缘的可用余量，避免溢出画布
    const limit = ringLimitAt(pos);
    const r =
      total > 1 && step > 0
        ? Math.min(limit, Math.max(ring, minGap / (2 * Math.sin(step / 2))))
        : Math.min(ring, limit);
    list.forEach((agent, i) => {
      const angle = total > 1 ? baseAngle - spread + i * step : baseAngle;
      push(agent, node.id, pos, r, angle);
    });
  });

  return { agents: placed };
}

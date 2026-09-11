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
    if (count === 0) return { id: node.id, x: cx, y: cy };
    // 从正上方（-90°）开始顺时针均匀分布
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / count;
    return {
      id: node.id,
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  });
  return {
    center: { x: cx, y: cy },
    nodes: positioned,
    radius,
  };
}

// 将「参与绘制」的 agent 以环绕形式布局到各自节点周围
// 返回：{ agents: [{ id, name, state, nodeId, x, y }] }
// options.ring：环绕半径；options.agentRingStart：起始角度（弧度）
export function layoutAgents(model, nodeLayout, options = {}) {
  const ring = Number(options.ring) || 34;
  const startAngle = Number(options.agentRingStart) || -Math.PI / 2;
  const placed = [];

  if (!model || !nodeLayout) return { agents: placed };

  const pushNodeAgents = (node, pos) => {
    const list = (node && node.drawAgents) || [];
    const total = list.length;
    if (total === 0) return;
    list.forEach((agent, i) => {
      // 围绕节点均匀分布
      const angle = startAngle + (i * 2 * Math.PI) / total;
      placed.push({
        id: agent.id,
        name: agent.name,
        type: agent.type || "agent",
        state: agent.state,
        nodeId: node.id,
        x: pos.x + ring * Math.cos(angle),
        y: pos.y + ring * Math.sin(angle),
      });
    });
  };

  const centerPos = nodeLayout.center;
  const posMap = new Map((nodeLayout.nodes || []).map((p) => [p.id, p]));
  if (model.center) pushNodeAgents(model.center, centerPos);
  (model.nodes || []).forEach((node) => {
    const pos = posMap.get(node.id);
    if (pos) pushNodeAgents(node, pos);
  });

  return { agents: placed };
}

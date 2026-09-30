// topology 的单元测试（零依赖，用 node 内置 test runner）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/components/topology.test.mjs   # 只跑本文件
//   node --test                                     # 自动发现全部 *.test.mjs
// 注意：不要用 `node --test src/`（目录参数在本 node 版本下不被支持）。
//
// 说明：topology.js 是拓扑图的数据模型与布局纯函数（无 Vue / 第三方依赖），
// 故可直接单测，不涉及 DOM。
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  NODE_STATE,
  AGENT_STATE,
  normalizeNodeStatus,
  normalizeAgentStatus,
  buildTopology,
  layoutTopology,
  layoutAgents,
  parseBrowserFromUserAgent,
  formatBrowserLabel,
} from "./topology.js";

// ===== normalizeNodeStatus =====
test("normalizeNodeStatus：online 别名归一为 online", () => {
  for (const v of [
    "online",
    "RUNNING",
    "ready",
    "connected",
    "up",
    " online ",
  ]) {
    assert.equal(normalizeNodeStatus(v), NODE_STATE.ONLINE, `输入 ${v}`);
  }
});

test("normalizeNodeStatus：offline 别名归一为 offline", () => {
  for (const v of ["offline", "stopped", "down", "disconnected", "DOWN"]) {
    assert.equal(normalizeNodeStatus(v), NODE_STATE.OFFLINE, `输入 ${v}`);
  }
});

test("normalizeNodeStatus：空值与未知值归一为 unknown", () => {
  assert.equal(normalizeNodeStatus(""), NODE_STATE.UNKNOWN);
  assert.equal(normalizeNodeStatus(null), NODE_STATE.UNKNOWN);
  assert.equal(normalizeNodeStatus(undefined), NODE_STATE.UNKNOWN);
  assert.equal(normalizeNodeStatus("whatever"), NODE_STATE.UNKNOWN);
});

// ===== normalizeAgentStatus =====
test("normalizeAgentStatus：各状态归一", () => {
  assert.equal(normalizeAgentStatus("stopped"), AGENT_STATE.STOPPED);
  assert.equal(normalizeAgentStatus("running"), AGENT_STATE.RUNNING);
  // 以 waiting 开头的任意状态类都归为 waiting
  assert.equal(normalizeAgentStatus("waiting"), AGENT_STATE.WAITING);
  assert.equal(normalizeAgentStatus("waiting-single"), AGENT_STATE.WAITING);
  assert.equal(normalizeAgentStatus("WAITING_CONFIRM"), AGENT_STATE.WAITING);
});

test("normalizeAgentStatus：空值与未知值归一为 idle", () => {
  assert.equal(normalizeAgentStatus(""), AGENT_STATE.IDLE);
  assert.equal(normalizeAgentStatus(null), AGENT_STATE.IDLE);
  assert.equal(normalizeAgentStatus("foo"), AGENT_STATE.IDLE);
});

// ===== buildTopology =====
test("buildTopology：无节点时自动补建 master（online）", () => {
  const model = buildTopology([], [], () => "running");
  assert.equal(model.center.id, "master");
  assert.equal(model.center.isCenter, true);
  assert.equal(model.center.state, NODE_STATE.ONLINE);
  assert.deepEqual(model.nodes, []);
  assert.deepEqual(model.links, []);
  assert.equal(model.counts.nodes, 1);
  assert.equal(model.counts.online, 1);
});

test("buildTopology：agent 按 node_id 归位，空 node_id 归 master", () => {
  const nodes = [{ node_id: "n1", status: "online" }];
  const agents = [
    { agent_id: "a1", name: "A1", node_id: "n1", agent_type: "code_agent" },
    { agent_id: "a2", name: "A2" }, // 无 node_id → master
  ];
  const model = buildTopology(nodes, agents, () => "running");
  assert.equal(model.center.agents.length, 1);
  assert.equal(model.center.agents[0].id, "a2");
  assert.equal(model.nodes.length, 1);
  assert.equal(model.nodes[0].id, "n1");
  assert.equal(model.nodes[0].agents.length, 1);
  assert.equal(model.nodes[0].agents[0].type, "code_agent");
  // 非 code_agent 一律归为 agent
  assert.equal(model.center.agents[0].type, "agent");
  // links 只连 master→子节点
  assert.deepEqual(model.links, [{ source: "master", target: "n1" }]);
});

test("buildTopology：stopped agent 计入 agents 但不计入 activeAgents/drawAgents", () => {
  const agents = [
    { agent_id: "a1", name: "A1", node_id: "master" },
    { agent_id: "a2", name: "A2", node_id: "master" },
  ];
  const getStatusClass = (a) => (a.agent_id === "a2" ? "stopped" : "running");
  const model = buildTopology([], agents, getStatusClass);
  assert.equal(model.counts.agents, 2);
  assert.equal(model.counts.activeAgents, 1);
  assert.equal(model.counts.stopped, 1);
  assert.equal(model.counts.running, 1);
  assert.equal(model.center.agents.length, 2);
  assert.equal(model.center.drawAgents.length, 1);
  assert.equal(model.center.drawAgents[0].id, "a1");
});

test("buildTopology：counts 各状态计数正确", () => {
  const agents = [
    { agent_id: "a1", node_id: "master" },
    { agent_id: "a2", node_id: "master" },
    { agent_id: "a3", node_id: "master" },
  ];
  const statusMap = { a1: "running", a2: "waiting-single", a3: "idle" };
  const model = buildTopology([], agents, (a) => statusMap[a.agent_id]);
  assert.deepEqual(model.counts, {
    nodes: 1,
    online: 1,
    agents: 3,
    activeAgents: 3,
    waiting: 1,
    running: 1,
    stopped: 0,
    idle: 1,
  });
});

test("buildTopology：非数组入参容错为空", () => {
  const model = buildTopology(null, undefined, null);
  assert.equal(model.center.id, "master");
  assert.deepEqual(model.nodes, []);
  assert.equal(model.counts.agents, 0);
});

// ===== layoutTopology =====
test("layoutTopology：默认画布 240，中心在正中", () => {
  const layout = layoutTopology({ nodes: [] }, 0, 0);
  assert.deepEqual(layout.center, { x: 120, y: 120 });
  assert.equal(layout.radius, Math.min(240, 240) * 0.34);
});

test("layoutTopology：单节点位于正上方（-90°）", () => {
  const layout = layoutTopology({ nodes: [{ id: "n1" }] }, 240, 240);
  const p = layout.nodes[0];
  assert.equal(p.id, "n1");
  assert.equal(p.angle, -Math.PI / 2);
  assert.ok(Math.abs(p.x - 120) < 1e-9);
  assert.ok(p.y < 120);
});

test("layoutTopology：多节点按圆周均匀分布", () => {
  const layout = layoutTopology(
    { nodes: [{ id: "n1" }, { id: "n2" }, { id: "n3" }, { id: "n4" }] },
    240,
    240,
  );
  assert.equal(layout.nodes.length, 4);
  // 相邻角度差为 2π/4
  const step = (2 * Math.PI) / 4;
  for (let i = 1; i < 4; i++) {
    assert.ok(
      Math.abs(layout.nodes[i].angle - layout.nodes[i - 1].angle - step) < 1e-9,
    );
  }
});

test("layoutTopology：radius 受 minRadius 下限约束，可被 options.radius 覆盖", () => {
  const layout = layoutTopology({ nodes: [] }, 240, 240, {
    centerHalfH: 50,
    nodeHalfH: 40,
    minGap: 20,
  });
  // minRadius = 50+40+20 = 110 > 240*0.34=81.6
  assert.equal(layout.radius, 110);

  const overridden = layoutTopology({ nodes: [] }, 240, 240, { radius: 300 });
  assert.equal(overridden.radius, 300);
});

// ===== layoutAgents =====
test("layoutAgents：空入参返回空 agents", () => {
  assert.deepEqual(layoutAgents(null, null), { agents: [] });
  assert.deepEqual(layoutAgents({}, null), { agents: [] });
});

test("layoutAgents：中心节点 agent 环绕一周", () => {
  const model = {
    center: {
      id: "master",
      drawAgents: [{ id: "a1", name: "A1", state: "running" }],
    },
    nodes: [],
  };
  const nodeLayout = { center: { x: 100, y: 100 }, nodes: [] };
  const { agents } = layoutAgents(model, nodeLayout, { centerRing: 30 });
  assert.equal(agents.length, 1);
  assert.equal(agents[0].nodeId, "master");
  // 单个 agent 位于 -90°（正上方）
  assert.ok(Math.abs(agents[0].x - 100) < 1e-9);
  assert.ok(agents[0].y < 100);
  assert.equal(agents[0].labelAnchor, "middle");
  assert.equal(agents[0].labelBaseline, "auto");
});

test("layoutAgents：子节点 agent 分布在背向中心扇形内", () => {
  const model = {
    center: { id: "master", drawAgents: [] },
    nodes: [
      {
        id: "n1",
        drawAgents: [
          { id: "a1", name: "A1", state: "running" },
          { id: "a2", name: "A2", state: "running" },
        ],
      },
    ],
  };
  // n1 位于正上方（angle=-90°），agent 应分布在朝外（上方）扇形
  const nodeLayout = {
    center: { x: 100, y: 100 },
    nodes: [{ id: "n1", x: 100, y: 40, angle: -Math.PI / 2 }],
  };
  const { agents } = layoutAgents(model, nodeLayout, { ring: 20 });
  assert.equal(agents.length, 2);
  for (const a of agents) {
    assert.equal(a.nodeId, "n1");
    // 扇形以 -90° 为中心，两侧各 spread，agent.y 应小于节点 y（在上方）
    assert.ok(a.y < 40);
  }
});

test("layoutAgents：labelAnchor / labelBaseline 按 cos/sin 边界取值", () => {
  // 中心 agent 角度从正上方(-90°)起顺时针均分：i=0 上、i=1 右、i=2 下、i=3 左
  const model = {
    center: {
      id: "master",
      drawAgents: [
        { id: "top", name: "T", state: "running" },
        { id: "right", name: "R", state: "running" },
        { id: "bottom", name: "B", state: "running" },
        { id: "left", name: "L", state: "running" },
      ],
    },
    nodes: [],
  };
  const nodeLayout = { center: { x: 0, y: 0 }, nodes: [] };
  const { agents } = layoutAgents(model, nodeLayout, { centerRing: 100 });
  const byId = Object.fromEntries(agents.map((a) => [a.id, a]));
  assert.equal(byId.top.labelAnchor, "middle");
  assert.equal(byId.top.labelBaseline, "auto");
  assert.equal(byId.right.labelAnchor, "start");
  assert.equal(byId.bottom.labelAnchor, "middle");
  assert.equal(byId.bottom.labelBaseline, "hanging");
  assert.equal(byId.left.labelAnchor, "end");
});

// ===== parseBrowserFromUserAgent =====
test("parseBrowserFromUserAgent：空 UA 返回空", () => {
  assert.deepEqual(parseBrowserFromUserAgent(""), { name: "", version: "" });
  assert.deepEqual(parseBrowserFromUserAgent(null), { name: "", version: "" });
  assert.deepEqual(parseBrowserFromUserAgent("Mozilla/5.0"), {
    name: "",
    version: "",
  });
});

test("parseBrowserFromUserAgent：各浏览器识别", () => {
  const cases = [
    ["Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36", "Chrome", "120.0.0.0"],
    ["Mozilla/5.0 Firefox/121.0", "Firefox", "121.0"],
    ["Mozilla/5.0 Version/17.0 Safari/605.1.15", "Safari", "17.0"],
    ["Mozilla/5.0 Edg/120.0.0.0", "Edge", "120.0.0.0"],
    ["Mozilla/5.0 OPR/105.0.0.0", "Opera", "105.0.0.0"],
    ["Mozilla/5.0 Vivaldi/6.5.3206.48", "Vivaldi", "6.5.3206.48"],
    ["Mozilla/5.0 YaBrowser/23.11.0.0", "Yandex", "23.11.0.0"],
  ];
  for (const [ua, name, version] of cases) {
    const r = parseBrowserFromUserAgent(ua);
    assert.equal(r.name, name, `UA=${ua}`);
    assert.equal(r.version, version, `UA=${ua}`);
  }
});

test("parseBrowserFromUserAgent：Edge/Opera 优先于 Chrome（UA 含 Chrome 标记）", () => {
  // Edge UA 同时含 Chrome 与 Safari，必须先匹配 Edge
  const edge = parseBrowserFromUserAgent(
    "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
  );
  assert.equal(edge.name, "Edge");
  const opera = parseBrowserFromUserAgent(
    "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 OPR/105.0.0.0",
  );
  assert.equal(opera.name, "Opera");
});

// ===== formatBrowserLabel =====
test("formatBrowserLabel：浏览器主版本 + 扩展版本", () => {
  assert.equal(
    formatBrowserLabel(
      { user_agent: "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36" },
      "5.0.5",
    ),
    "Chrome 120 · v5.0.5",
  );
});

test("formatBrowserLabel：无扩展版本时只显示浏览器", () => {
  assert.equal(
    formatBrowserLabel(
      { user_agent: "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36" },
      "",
    ),
    "Chrome 120",
  );
});

test("formatBrowserLabel：无浏览器信息时只显示扩展版本", () => {
  assert.equal(formatBrowserLabel({}, "5.0.5"), "v5.0.5");
  assert.equal(formatBrowserLabel(null, "5.0.5"), "v5.0.5");
});

test("formatBrowserLabel：全空返回空串", () => {
  assert.equal(formatBrowserLabel(null, ""), "");
  assert.equal(formatBrowserLabel({ user_agent: "" }, ""), "");
});

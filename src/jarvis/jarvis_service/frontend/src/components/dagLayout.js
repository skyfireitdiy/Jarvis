// 流水线 DAG 分层布局（纯 JS，无 Vue / 第三方依赖）。
//
// 输入 stages（数组或 Map 的 values），每项含 { stage, dependsOn: [...] }。
// 输出分层坐标与连线，供 OrchestrationView 自绘 SVG 使用。
//
// 布局策略：
// - level：无依赖=0；否则 1 + max(依赖的 level)。含环防御（回退按声明顺序）。
// - 同层节点按声明顺序纵向排列（y 递增），层间横向展开（x 递增）。

export const LAYOUT = {
  NODE_W: 180,
  NODE_H: 64,
  GAP_X: 90,
  GAP_Y: 28,
  PAD_X: 24,
  PAD_Y: 24,
};

// 计算每个 stage 的层级（含环防御）。
export function computeLevels(stages) {
  const list = normalizeStages(stages);
  const byStage = new Map(list.map((s) => [s.stage, s]));
  const levelCache = new Map();

  function levelOf(stage, visiting) {
    if (levelCache.has(stage)) return levelCache.get(stage);
    if (visiting.has(stage)) return 0; // 环：回退，避免无限递归
    const node = byStage.get(stage);
    if (!node) return 0;
    visiting.add(stage);
    let maxDep = -1;
    for (const d of node.dependsOn) {
      if (!byStage.has(d)) continue;
      maxDep = Math.max(maxDep, levelOf(d, visiting));
    }
    visiting.delete(stage);
    const level = maxDep < 0 ? 0 : maxDep + 1;
    levelCache.set(stage, level);
    return level;
  }

  const levels = new Map();
  for (const s of list) levels.set(s.stage, levelOf(s.stage, new Set()));
  return levels;
}

function normalizeStages(stages) {
  let arr = [];
  if (stages instanceof Map) arr = [...stages.values()];
  else if (Array.isArray(stages)) arr = stages;
  else if (stages && typeof stages === "object") arr = Object.values(stages);
  return arr
    .filter((s) => s && s.stage)
    .map((s) => ({
      stage: s.stage,
      dependsOn: Array.isArray(s.dependsOn)
        ? s.dependsOn
        : Array.isArray(s.depends_on)
          ? s.depends_on
          : [],
    }));
}

// 计算布局：返回 { width, height, positions: {stage:{x,y}}, edges:[{from,to}], levels }。
export function layoutDag(stages) {
  const list = normalizeStages(stages);
  const levels = computeLevels(list);

  // 按 level 分组，组内保持声明顺序
  const columns = new Map();
  for (const s of list) {
    const lv = levels.get(s.stage) || 0;
    if (!columns.has(lv)) columns.set(lv, []);
    columns.get(lv).push(s.stage);
  }
  const maxLevel = columns.size ? Math.max(...columns.keys()) : 0;
  const maxRows = columns.size
    ? Math.max(...[...columns.values()].map((c) => c.length))
    : 0;

  const positions = {};
  for (const [lv, stagesInCol] of columns.entries()) {
    const colH = stagesInCol.length * LAYOUT.NODE_H + (stagesInCol.length - 1) * LAYOUT.GAP_Y;
    const totalH = maxRows * LAYOUT.NODE_H + (maxRows - 1) * LAYOUT.GAP_Y;
    const startY = LAYOUT.PAD_Y + (totalH - colH) / 2;
    stagesInCol.forEach((stage, i) => {
      positions[stage] = {
        x: LAYOUT.PAD_X + lv * (LAYOUT.NODE_W + LAYOUT.GAP_X),
        y: startY + i * (LAYOUT.NODE_H + LAYOUT.GAP_Y),
        level: lv,
      };
    });
  }

  const edges = [];
  for (const s of list) {
    for (const d of s.dependsOn) {
      if (positions[d] && positions[s.stage]) {
        edges.push({ from: d, to: s.stage });
      }
    }
  }

  const width = LAYOUT.PAD_X * 2 + (maxLevel + 1) * LAYOUT.NODE_W + maxLevel * LAYOUT.GAP_X;
  const height =
    LAYOUT.PAD_Y * 2 + Math.max(maxRows, 1) * LAYOUT.NODE_H + Math.max(maxRows - 1, 0) * LAYOUT.GAP_Y;

  return { width, height, positions, edges, levels };
}

// 生成连接 from→to 的三次贝塞尔路径（水平流向）。
export function edgePath(fromPos, toPos) {
  const x1 = fromPos.x + LAYOUT.NODE_W;
  const y1 = fromPos.y + LAYOUT.NODE_H / 2;
  const x2 = toPos.x;
  const y2 = toPos.y + LAYOUT.NODE_H / 2;
  const dx = Math.max((x2 - x1) / 2, 20);
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

// dagLayout 的单元测试（零依赖，用 node 内置 test runner）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/components/dagLayout.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { computeLevels, layoutDag, edgePath, LAYOUT } from "./dagLayout.js";

test("computeLevels：线性依赖逐级递增", () => {
  const levels = computeLevels([
    { stage: "a", dependsOn: [] },
    { stage: "b", dependsOn: ["a"] },
    { stage: "c", dependsOn: ["b"] },
  ]);
  assert.equal(levels.get("a"), 0);
  assert.equal(levels.get("b"), 1);
  assert.equal(levels.get("c"), 2);
});

test("computeLevels：并行分支取依赖最大层级", () => {
  const levels = computeLevels([
    { stage: "a", dependsOn: [] },
    { stage: "b", dependsOn: ["a"] },
    { stage: "c", dependsOn: ["a"] },
    { stage: "d", dependsOn: ["b", "c"] },
  ]);
  assert.equal(levels.get("b"), 1);
  assert.equal(levels.get("c"), 1);
  assert.equal(levels.get("d"), 2);
});

test("computeLevels：环防御不无限递归", () => {
  const levels = computeLevels([
    { stage: "a", dependsOn: ["b"] },
    { stage: "b", dependsOn: ["a"] },
  ]);
  assert.ok(levels.has("a"));
  assert.ok(levels.has("b"));
});

test("computeLevels：忽略不存在的依赖", () => {
  const levels = computeLevels([{ stage: "a", dependsOn: ["ghost"] }]);
  assert.equal(levels.get("a"), 0);
});

test("layoutDag：同层节点 y 递增、层间 x 递增", () => {
  const { positions } = layoutDag([
    { stage: "a", dependsOn: [] },
    { stage: "b", dependsOn: [] },
    { stage: "c", dependsOn: ["a", "b"] },
  ]);
  assert.equal(positions.a.x, positions.b.x);
  assert.ok(positions.b.y > positions.a.y);
  assert.ok(positions.c.x > positions.a.x);
});

test("layoutDag：edges 覆盖所有合法依赖，忽略悬空依赖", () => {
  const { edges } = layoutDag([
    { stage: "a", dependsOn: [] },
    { stage: "b", dependsOn: ["a", "ghost"] },
  ]);
  assert.deepEqual(edges, [{ from: "a", to: "b" }]);
});

test("layoutDag：width/height 为正且随节点数增长", () => {
  const single = layoutDag([{ stage: "a", dependsOn: [] }]);
  const chain = layoutDag([
    { stage: "a", dependsOn: [] },
    { stage: "b", dependsOn: ["a"] },
    { stage: "c", dependsOn: ["b"] },
  ]);
  assert.ok(single.width > 0 && single.height > 0);
  assert.ok(chain.width > single.width);
});

test("layoutDag：支持 Map 输入", () => {
  const stages = new Map([
    ["a", { stage: "a", dependsOn: [] }],
    ["b", { stage: "b", dependsOn: ["a"] }],
  ]);
  const { positions } = layoutDag(stages);
  assert.ok(positions.a && positions.b);
  assert.ok(positions.b.x > positions.a.x);
});

test("edgePath：生成三次贝塞尔路径", () => {
  const p = edgePath({ x: 0, y: 0 }, { x: 300, y: 100 });
  assert.ok(p.startsWith("M "));
  assert.ok(p.includes(" C "));
  assert.ok(p.includes(String(LAYOUT.NODE_W))); // 起点 x 从节点右边缘出发
});

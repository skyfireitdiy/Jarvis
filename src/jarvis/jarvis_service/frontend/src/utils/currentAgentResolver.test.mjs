// currentAgentResolver 的单元测试（零依赖，用 node 内置 test runner）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/utils/currentAgentResolver.test.mjs   # 只跑本文件
//   npm run test:node                                      # 跑全部 *.test.mjs
//
// 背景：命令面板 / 右键菜单的「当前 Agent」组动作都靠 resolveCurrentAgentId 定位作用对象。
// 曾出过的 bug：解析时把「右键菜单可见」也作为锁定条件，导致点击菜单项（菜单先收起）
// 后锁定失效、回退到当前活动 Agent，删除/重命名作用到错误对象。下面用回归用例锁死该行为。
import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveCurrentAgentId } from "./currentAgentResolver.js";

test("无任何状态时返回 null", () => {
  assert.equal(resolveCurrentAgentId({}), null);
  assert.equal(resolveCurrentAgentId(), null);
});

test("右键锁定的 Agent 优先级最高（覆盖其它所有状态）", () => {
  const id = resolveCurrentAgentId({
    contextMenuAgentId: "right-clicked",
    lobbyActiveAgentId: "lobby",
    hasNoPanel: true,
    activePanelAgentId: "active-panel",
    currentAgentId: "current",
  });
  assert.equal(id, "right-clicked");
});

test("回归：右键锁定不依赖菜单可见性——仅传 contextMenuAgentId 即生效", () => {
  // 菜单项被点击时菜单会先收起（visible=false），解析不应因此回退到当前活动 Agent。
  // 这里不传任何「菜单可见」字段，锁定仍须生效。
  const id = resolveCurrentAgentId({
    contextMenuAgentId: "right-clicked",
    activePanelAgentId: "active-panel",
    currentAgentId: "current",
  });
  assert.equal(id, "right-clicked");
});

test("回归：右键锁定优先于当前激活 Panel（删除作用于被右键的 Agent）", () => {
  // 场景：当前激活 Panel 是 agent-B，但用户在侧边栏右键了 agent-A 并点删除。
  const id = resolveCurrentAgentId({
    contextMenuAgentId: "agent-A",
    activePanelAgentId: "agent-B",
    currentAgentId: "agent-B",
  });
  assert.equal(id, "agent-A");
});

test("纯大厅态（无面板）：以大厅选中的宠物为准", () => {
  const id = resolveCurrentAgentId({
    hasNoPanel: true,
    lobbyActiveAgentId: "lobby-pet",
    activePanelAgentId: "active-panel",
    currentAgentId: "current",
  });
  assert.equal(id, "lobby-pet");
});

test("有面板时：hasNoPanel=false 不启用大厅优先，改用激活 Panel", () => {
  const id = resolveCurrentAgentId({
    hasNoPanel: false,
    lobbyActiveAgentId: "lobby-pet",
    activePanelAgentId: "active-panel",
    currentAgentId: "current",
  });
  assert.equal(id, "active-panel");
});

test("无激活 Panel 时回退到大厅选中宠物", () => {
  const id = resolveCurrentAgentId({
    hasNoPanel: false,
    lobbyActiveAgentId: "lobby-pet",
    activePanelAgentId: null,
    currentAgentId: "current",
  });
  assert.equal(id, "lobby-pet");
});

test("仅有 currentAgentId 时用它兜底", () => {
  const id = resolveCurrentAgentId({
    currentAgentId: "current",
  });
  assert.equal(id, "current");
});

test("contextMenuAgentId 为 null/空串时视为未锁定", () => {
  assert.equal(
    resolveCurrentAgentId({
      contextMenuAgentId: null,
      currentAgentId: "current",
    }),
    "current",
  );
  assert.equal(
    resolveCurrentAgentId({
      contextMenuAgentId: "",
      currentAgentId: "current",
    }),
    "current",
  );
});

test("lobbyActiveAgentId 为空串时不参与解析", () => {
  const id = resolveCurrentAgentId({
    hasNoPanel: true,
    lobbyActiveAgentId: "",
    currentAgentId: "current",
  });
  assert.equal(id, "current");
});

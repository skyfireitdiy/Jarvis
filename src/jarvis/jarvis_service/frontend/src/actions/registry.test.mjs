// actions/registry 的单元测试（零依赖，用 node 内置 test runner）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/actions/registry.test.mjs   # 只跑本文件
//   npm run test:node                           # 跑全部 node:test 用例
//
// 说明：registry 是命令面板 / 宠物菜单 / 快捷键共用的「单一数据源」，
// 纯模块不依赖 Vue 与 DOM，故直接对纯函数与数据表做单测。
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ACTIONS,
  filterActions,
  groupActions,
  findShortcutConflicts,
} from "./registry.js";

// ===== filterActions =====

test("filterActions：空 query 返回浅拷贝（新数组、元素同一引用）", () => {
  const src = [{ id: "a" }, { id: "b" }];
  const out = filterActions(src, "");
  assert.notEqual(out, src); // 必须是新数组，避免调用方误改原表
  assert.deepEqual(out, src);
  assert.equal(out[0], src[0]); // 元素仍是同一引用
});

test("filterActions：null/undefined query 视为空查询", () => {
  const src = [{ id: "a", label: "A" }];
  assert.equal(filterActions(src, null).length, 1);
  assert.equal(filterActions(src, undefined).length, 1);
});

test("filterActions：query 首尾空格与大小写归一", () => {
  const src = [{ id: "view-diff", label: "查看变更", en: "View Diff" }];
  assert.equal(filterActions(src, "  VIEW  ").length, 1);
  assert.equal(filterActions(src, "view").length, 1);
});

test("filterActions：可匹配 label / en / id / group / keywords 任一字段", () => {
  const src = [
    {
      id: "x1",
      label: "查看变更",
      en: "View Diff",
      group: "当前 Agent",
      keywords: ["改动"],
    },
  ];
  assert.equal(filterActions(src, "查看").length, 1); // label
  assert.equal(filterActions(src, "diff").length, 1); // en（大小写不敏感）
  assert.equal(filterActions(src, "x1").length, 1); // id
  assert.equal(filterActions(src, "agent").length, 1); // group
  assert.equal(filterActions(src, "改动").length, 1); // keywords
  assert.equal(filterActions(src, "不存在的词").length, 0);
});

test("filterActions：非数组入参容错为空数组", () => {
  assert.deepEqual(filterActions(null, "x"), []);
  assert.deepEqual(filterActions(undefined, "x"), []);
  assert.deepEqual(filterActions("not-array", "x"), []);
});

test("filterActions：条目缺字段时不报错（filter(Boolean) 兜底）", () => {
  const src = [{ id: "only-id" }, { label: "只有标签" }, {}];
  assert.equal(filterActions(src, "only-id").length, 1);
  assert.equal(filterActions(src, "只有标签").length, 1);
  assert.equal(filterActions(src, "zzz").length, 0);
});

// ===== groupActions =====

test("groupActions：按 group 聚合，保持组内与组的首次出现顺序", () => {
  const src = [
    { id: "a", group: "G1" },
    { id: "b", group: "G2" },
    { id: "c", group: "G1" },
  ];
  const out = groupActions(src);
  assert.deepEqual(
    out.map((g) => g.group),
    ["G1", "G2"],
  );
  assert.deepEqual(
    out[0].actions.map((a) => a.id),
    ["a", "c"],
  );
  assert.deepEqual(
    out[1].actions.map((a) => a.id),
    ["b"],
  );
});

test("groupActions：group 缺失归入「其他」", () => {
  const out = groupActions([{ id: "a" }, { id: "b", group: "" }]);
  assert.equal(out.length, 1);
  assert.equal(out[0].group, "其他");
  assert.equal(out[0].actions.length, 2);
});

test("groupActions：非数组入参返回空数组", () => {
  assert.deepEqual(groupActions(null), []);
  assert.deepEqual(groupActions("x"), []);
});

// ===== findShortcutConflicts =====

test("findShortcutConflicts：真实注册表当前无快捷键冲突（回归防线）", () => {
  const conflicts = findShortcutConflicts();
  assert.ok(Array.isArray(conflicts));
  assert.deepEqual(
    conflicts,
    [],
    `注册表存在无法区分的同键动作：${JSON.stringify(conflicts)}`,
  );
});

test("findShortcutConflicts：同键且 scope 重复 → 报冲突", () => {
  const actions = [
    { id: "a", shortcut: "Ctrl+K", shortcutScope: "global" },
    { id: "b", shortcut: "ctrl+k", shortcutScope: "global" },
  ];
  const conflicts = findShortcutConflicts(actions);
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].shortcut, "ctrl+k"); // 键名小写归一
  assert.match(conflicts[0].reason, /global/);
  assert.deepEqual(conflicts[0].actions, ["a", "b"]);
});

test("findShortcutConflicts：同键但 scope 互不相同 → 不报冲突", () => {
  const actions = [
    { id: "a", shortcut: "F2", shortcutScope: "global" },
    { id: "b", shortcut: "F2", shortcutScope: "node" },
  ];
  assert.deepEqual(findShortcutConflicts(actions), []);
});

test("findShortcutConflicts：未声明 scope 视为 global，与显式 global 冲突", () => {
  const actions = [
    { id: "a", shortcut: "F2" },
    { id: "b", shortcut: "F2", shortcutScope: "global" },
  ];
  const conflicts = findShortcutConflicts(actions);
  assert.equal(conflicts.length, 1);
  assert.deepEqual(conflicts[0].actions, ["a", "b"]);
});

test("findShortcutConflicts：无 shortcut 的动作被忽略；非数组入参不抛错", () => {
  assert.deepEqual(
    findShortcutConflicts([{ id: "a" }, { id: "b", shortcut: "" }]),
    [],
  );
  assert.deepEqual(findShortcutConflicts(null), []);
  assert.deepEqual(findShortcutConflicts("x"), []);
});

// ===== ACTIONS 数据表自检 =====

test("ACTIONS：每项含 id/label/group/icon/run 且 id 唯一", () => {
  assert.ok(Array.isArray(ACTIONS));
  assert.ok(ACTIONS.length > 0);
  const ids = ACTIONS.map((a) => a.id);
  assert.equal(new Set(ids).size, ids.length, "存在重复 id");
  for (const action of ACTIONS) {
    assert.equal(
      typeof action.id,
      "string",
      `id 非字符串：${JSON.stringify(action)}`,
    );
    assert.ok(action.id.length > 0, "id 为空");
    assert.equal(typeof action.label, "string", `label 非字符串：${action.id}`);
    assert.ok(action.label.length > 0, `label 为空：${action.id}`);
    assert.equal(typeof action.group, "string", `group 非字符串：${action.id}`);
    assert.equal(typeof action.icon, "string", `icon 非字符串：${action.id}`);
    assert.equal(typeof action.run, "function", `run 非函数：${action.id}`);
  }
});

// historyStorage 的单元测试（零依赖，用 node 内置 test runner）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/historyStorage.test.mjs   # 只跑本文件
//   npm run test:node                         # 跑全部 node:test 用例
//
// 说明：historyStorage 是对话历史在 localStorage 上的持久化工具。
// node:test 环境没有 localStorage，这里挂一个最小内存实现（Map 语义、
// 值按字符串存取），行为对齐浏览器 localStorage 的常用子集。
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";

// ===== localStorage 内存桩（必须在 import 被测模块之前挂到 globalThis）=====
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(String(k)) ? store.get(String(k)) : null),
  setItem: (k, v) => {
    store.set(String(k), String(v));
  },
  removeItem: (k) => {
    store.delete(String(k));
  },
  clear: () => store.clear(),
};

const historyStorage = (await import("./historyStorage.js")).default;
const {
  saveMessage,
  saveMessages,
  loadHistory,
  getTotalCount,
  clearHistory,
  clearHistoryForAgent,
  getHistoryForAgent,
  setHistoryForAgent,
  getMetadata,
  updateMetadata,
  getStorageInfo,
  MAX_MESSAGES_PER_PAGE,
  MAX_TOTAL_MESSAGES,
} = historyStorage;

const STORAGE_KEY = "jarvis_chat_history";
const METADATA_KEY = "jarvis_chat_metadata";

// 每个用例前清空存储，避免相互污染
beforeEach(() => {
  localStorage.clear();
});

// 直接读取底层存储，用于断言真实落盘内容
const rawMessages = () => JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");

// ===== 常量 =====

test("导出常量：MAX_MESSAGES_PER_PAGE=50、MAX_TOTAL_MESSAGES=1000", () => {
  assert.equal(MAX_MESSAGES_PER_PAGE, 50);
  assert.equal(MAX_TOTAL_MESSAGES, 1000);
});

// ===== saveMessage =====

test("saveMessage：新消息自动补 id 与 storageTimestamp 并追加", () => {
  const ok = saveMessage({ agent_id: "a1", content: "hi" });
  assert.equal(ok, true);
  const saved = rawMessages();
  assert.equal(saved.length, 1);
  assert.equal(saved[0].agent_id, "a1");
  assert.ok(saved[0].id, "应自动生成 id");
  assert.ok(saved[0].storageTimestamp, "应自动写入 storageTimestamp");
});

test("saveMessage：同 id 走更新，不新增且就地替换", () => {
  saveMessage({ id: "m1", content: "old" });
  saveMessage({ id: "m1", content: "new" });
  const saved = rawMessages();
  assert.equal(saved.length, 1);
  assert.equal(saved[0].content, "new");
});

test("saveMessage：超过 MAX_TOTAL_MESSAGES 时从头截断", () => {
  for (let i = 0; i < MAX_TOTAL_MESSAGES + 5; i++) {
    saveMessage({ id: `m${i}`, content: `c${i}` });
  }
  const saved = rawMessages();
  assert.equal(saved.length, MAX_TOTAL_MESSAGES);
  // 最早的 5 条被丢弃，首条应为 m5
  assert.equal(saved[0].id, "m5");
  assert.equal(saved[saved.length - 1].id, `m${MAX_TOTAL_MESSAGES + 4}`);
});

// ===== saveMessages =====

test("saveMessages：批量追加，无 id 的补 id", () => {
  const ok = saveMessages([{ content: "a" }, { content: "b" }]);
  assert.equal(ok, true);
  const saved = rawMessages();
  assert.equal(saved.length, 2);
  assert.ok(saved[0].id);
  assert.ok(saved[1].id);
});

test("saveMessages：已存在 id 的条目被跳过（不覆盖）", () => {
  saveMessage({ id: "m1", content: "original" });
  saveMessages([
    { id: "m1", content: "should-not-apply" },
    { id: "m2", content: "new" },
  ]);
  const saved = rawMessages();
  assert.equal(saved.length, 2);
  assert.equal(saved.find((m) => m.id === "m1").content, "original");
  assert.equal(saved.find((m) => m.id === "m2").content, "new");
});

// ===== loadHistory =====

test("loadHistory：空存储返回 []", () => {
  assert.deepEqual(loadHistory(), []);
});

test("loadHistory：默认取末尾 50 条", () => {
  for (let i = 0; i < 60; i++) saveMessage({ id: `m${i}` });
  const page = loadHistory();
  assert.equal(page.length, MAX_MESSAGES_PER_PAGE);
  assert.equal(page[0].id, "m10"); // 从末尾往前 50 条 → m10..m59
  assert.equal(page[page.length - 1].id, "m59");
});

test("loadHistory：offset 从末尾往前跳过", () => {
  for (let i = 0; i < 10; i++) saveMessage({ id: `m${i}` });
  const page = loadHistory(3, 2); // 跳过末尾 2 条，再取 3 条
  assert.deepEqual(
    page.map((m) => m.id),
    ["m5", "m6", "m7"],
  );
});

test("loadHistory：指定 agentId 只返回该 agent 的消息", () => {
  saveMessage({ id: "a1", agent_id: "A" });
  saveMessage({ id: "b1", agent_id: "B" });
  saveMessage({ id: "a2", agent_id: "A" });
  const page = loadHistory(50, 0, "A");
  assert.deepEqual(
    page.map((m) => m.id),
    ["a1", "a2"],
  );
});

test("loadHistory：offset 超过总数时返回 []", () => {
  saveMessage({ id: "m0" });
  assert.deepEqual(loadHistory(50, 5), []);
});

// ===== getTotalCount =====

test("getTotalCount：总数与按 agentId 过滤计数", () => {
  saveMessage({ id: "a1", agent_id: "A" });
  saveMessage({ id: "b1", agent_id: "B" });
  saveMessage({ id: "a2", agent_id: "A" });
  assert.equal(getTotalCount(), 3);
  assert.equal(getTotalCount("A"), 2);
  assert.equal(getTotalCount("不存在"), 0);
});

// ===== clearHistory / clearHistoryForAgent =====

test("clearHistory：清空消息与元数据两个 key", () => {
  saveMessage({ id: "m0" });
  updateMetadata();
  assert.equal(clearHistory(), true);
  assert.equal(localStorage.getItem(STORAGE_KEY), null);
  assert.equal(localStorage.getItem(METADATA_KEY), null);
});

test("clearHistoryForAgent：只删指定 agent，其它保留", () => {
  saveMessage({ id: "a1", agent_id: "A" });
  saveMessage({ id: "b1", agent_id: "B" });
  assert.equal(clearHistoryForAgent("A"), true);
  const saved = rawMessages();
  assert.equal(saved.length, 1);
  assert.equal(saved[0].id, "b1");
});

test("clearHistoryForAgent：目标不存在时也返回 true", () => {
  saveMessage({ id: "b1", agent_id: "B" });
  assert.equal(clearHistoryForAgent("不存在"), true);
  assert.equal(rawMessages().length, 1);
});

// ===== getHistoryForAgent / setHistoryForAgent =====

test("getHistoryForAgent：只返回指定 agent 的消息", () => {
  saveMessage({ id: "a1", agent_id: "A" });
  saveMessage({ id: "b1", agent_id: "B" });
  assert.deepEqual(
    getHistoryForAgent("A").map((m) => m.id),
    ["a1"],
  );
  assert.deepEqual(getHistoryForAgent("不存在"), []);
});

test("setHistoryForAgent：移除该 agent 旧消息并写入新消息，其它 agent 不受影响", () => {
  saveMessage({ id: "a1", agent_id: "A" });
  saveMessage({ id: "b1", agent_id: "B" });
  const ok = setHistoryForAgent("A", [{ content: "new-a" }]);
  assert.equal(ok, true);
  const saved = rawMessages();
  // B 保留，A 的旧消息被替换为一条新消息
  const bMessages = saved.filter((m) => m.agent_id === "B");
  const aMessages = saved.filter((m) => m.agent_id === "A");
  assert.equal(bMessages.length, 1);
  assert.equal(bMessages[0].id, "b1");
  assert.equal(aMessages.length, 1);
  assert.equal(aMessages[0].content, "new-a");
  assert.ok(aMessages[0].id, "新消息应补 id");
  assert.ok(aMessages[0].storageTimestamp, "新消息应补 storageTimestamp");
  assert.ok(!saved.some((m) => m.id === "a1"), "旧消息 a1 应被移除");
});

// ===== getMetadata / updateMetadata =====

test("getMetadata：无数据时返回默认对象", () => {
  assert.deepEqual(getMetadata(), {
    totalCount: 0,
    lastUpdated: null,
    storageSize: 0,
  });
});

test("updateMetadata：写入 totalCount 与 storageSize", () => {
  saveMessage({ id: "m0", content: "x" });
  const meta = updateMetadata();
  assert.equal(meta.totalCount, 1);
  assert.ok(meta.lastUpdated > 0);
  assert.equal(meta.storageSize, JSON.stringify(rawMessages()).length);
  // 落盘并可读回
  assert.deepEqual(getMetadata(), meta);
});

// ===== getStorageInfo =====

test("getStorageInfo：空存储时 lastUpdated 为「从未」、maxMessages=1000", () => {
  const info = getStorageInfo();
  assert.equal(info.totalCount, 0);
  assert.equal(info.lastUpdated, "从未");
  assert.equal(info.maxMessages, MAX_TOTAL_MESSAGES);
  // 注意：空存储时 getAllMessages() 返回 []，JSON.stringify([]) === "[]"（长度 2），
  // 故 totalSize 为 2 而非 0，formatBytes(2) 得 "2 B"。这是现有实现的真实行为。
  assert.equal(info.totalSize, 2);
  assert.equal(info.totalSizeFormatted, "2 B");
});

test("getStorageInfo：有数据时统计数量与体积", () => {
  saveMessage({ id: "m0" });
  const info = getStorageInfo();
  assert.equal(info.totalCount, 1);
  assert.ok(info.totalSize > 0);
  assert.match(info.totalSizeFormatted, /B$/);
});

// ===== 异常容错 =====

test("异常容错：localStorage.getItem 抛错时读取路径返回空/默认值且不抛", () => {
  const original = globalThis.localStorage;
  globalThis.localStorage = {
    getItem: () => {
      throw new Error("boom");
    },
    setItem: () => {},
    removeItem: () => {},
    clear: () => {},
  };
  try {
    assert.deepEqual(loadHistory(), []);
    assert.equal(getTotalCount(), 0);
    assert.deepEqual(getHistoryForAgent("A"), []);
    assert.deepEqual(getMetadata(), {
      totalCount: 0,
      lastUpdated: null,
      storageSize: 0,
    });
    assert.equal(getStorageInfo().totalCount, 0);
  } finally {
    globalThis.localStorage = original;
  }
});

test("异常容错：localStorage.setItem 抛错时不向外抛（saveMessage 仍返回 true）", () => {
  const original = globalThis.localStorage;
  globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {
      throw new Error("quota exceeded");
    },
    removeItem: () => {},
    clear: () => {},
  };
  try {
    // 注意：saveMessage/saveMessages 内部调用 saveAllMessages 但未检查其返回值，
    // 因此底层写入失败时仍返回 true（写入失败仅被 saveAllMessages 内部捕获并打印）。
    // 这里如实断言现有行为——不掩盖、也不夹带修复。
    assert.equal(saveMessage({ content: "x" }), true);
    assert.equal(saveMessages([{ content: "y" }]), true);
  } finally {
    globalThis.localStorage = original;
  }
});

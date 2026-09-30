// configYaml 的单元测试（零依赖，用 node 内置 test runner）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/utils/configYaml.test.mjs   # 只跑本文件
//   node --test                                 # 自动发现全部 *.test.mjs
// 注意：不要用 `node --test src/`（目录参数在本 node 版本下不被支持）。
//
// 说明：configYaml 是配置编辑器（ConfigEditorModal）依赖的纯文本 YAML
// 序列化/解析工具，不涉及 DOM，故可直接对纯函数做单测。
import { test } from "node:test";
import assert from "node:assert/strict";
import { cloneValue, toYaml, parseYaml } from "./configYaml.js";

// ===== cloneValue =====
test("cloneValue：原始值原样返回", () => {
  assert.equal(cloneValue(1), 1);
  assert.equal(cloneValue("a"), "a");
  assert.equal(cloneValue(true), true);
  assert.equal(cloneValue(null), null);
  assert.equal(cloneValue(undefined), undefined);
});

test("cloneValue：对象/数组深拷贝，修改副本不影响原值", () => {
  const src = { a: 1, b: { c: [1, 2] } };
  const copy = cloneValue(src);
  assert.deepEqual(copy, src);
  copy.b.c.push(3);
  assert.deepEqual(src.b.c, [1, 2]);
});

// ===== toYaml =====
test("toYaml：标量", () => {
  assert.equal(toYaml(null), "null");
  assert.equal(toYaml(undefined), "null");
  assert.equal(toYaml(42), "42");
  assert.equal(toYaml(true), "true");
  assert.equal(toYaml("hello"), "hello");
});

test("toYaml：空数组与空对象", () => {
  assert.equal(toYaml([]), "[]");
  assert.equal(toYaml({}), "{}");
});

test("toYaml：字符串引号规则（保留词与特殊字符需引号）", () => {
  // 普通词不加引号
  assert.equal(toYaml("abc"), "abc");
  assert.equal(toYaml("中文值"), "中文值");
  // 会被误解析为布尔/空值的词必须加引号
  assert.equal(toYaml("true"), '"true"');
  assert.equal(toYaml("false"), '"false"');
  assert.equal(toYaml("null"), '"null"');
  assert.equal(toYaml("yes"), '"yes"');
  assert.equal(toYaml("off"), '"off"');
  // 空串用单引号
  assert.equal(toYaml(""), "''");
  // 含冒号等特殊字符走 JSON 引号
  assert.equal(toYaml("a:b"), '"a:b"');
});

test("toYaml：嵌套对象", () => {
  const out = toYaml({ a: 1, b: { c: 2 } });
  assert.equal(out, "a: 1\nb:\n  c: 2");
});

test("toYaml：数组（标量项）", () => {
  assert.equal(toYaml([1, 2, 3]), "- 1\n- 2\n- 3");
});

test("toYaml：数组含对象项，首行键对齐到「- 」之后", () => {
  const out = toYaml([{ name: "x", v: 1 }]);
  assert.equal(out, "- name: x\n  v: 1");
});

test("toYaml：键名的引号规则", () => {
  // 含空格：yamlQuote 认为可安全裸写，不加引号（YAML 中键可含空格）
  assert.equal(toYaml({ "a b": 1 }), "a b: 1");
  // 常规字符不加引号
  assert.equal(toYaml({ "a.b": 1 }), "a.b: 1");
  // 含冒号等会破坏结构的字符需加引号
  assert.equal(toYaml({ "a:b": 1 }), '"a:b": 1');
});

// ===== parseYaml =====
test("parseYaml：空输入返回空对象", () => {
  assert.deepEqual(parseYaml(""), {});
  assert.deepEqual(parseYaml("\n\n"), {});
});

test("parseYaml：跳过注释与空行", () => {
  const out = parseYaml("# 注释\n\na: 1\n  # 缩进注释\nb: 2");
  assert.deepEqual(out, { a: 1, b: 2 });
});

test("parseYaml：标量类型推断", () => {
  const out = parseYaml(
    [
      "i: 10",
      "neg: -3",
      "f: 1.5",
      "t: true",
      "fa: false",
      "n: null",
      "s: abc",
    ].join("\n"),
  );
  assert.deepEqual(out, {
    i: 10,
    neg: -3,
    f: 1.5,
    t: true,
    fa: false,
    n: null,
    s: "abc",
  });
});

test("parseYaml：嵌套容器按缩进归位", () => {
  const out = parseYaml(
    ["a:", "  b: 1", "  c:", "    d: 2", "e: 3"].join("\n"),
  );
  assert.deepEqual(out, { a: { b: 1, c: { d: 2 } }, e: 3 });
});

test("parseYaml：引号字符串（双引号/单引号）", () => {
  const out = parseYaml(['a: "true"', "b: '123'", 'c: "a:b"'].join("\n"));
  assert.deepEqual(out, { a: "true", b: "123", c: "a:b" });
});

test("parseYaml：键名含特殊字符（带引号）", () => {
  const out = parseYaml('"a b": 1');
  assert.deepEqual(out, { "a b": 1 });
});

test("parseYaml：与 toYaml 往返一致（标量 + 嵌套）", () => {
  const src = { name: "agent", count: 3, nested: { flag: true, list: "x" } };
  assert.deepEqual(parseYaml(toYaml(src)), src);
});

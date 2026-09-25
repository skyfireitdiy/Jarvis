// gitDiffParser 的单元测试（零依赖，用 node 内置 test runner）。
//
// 运行方式（在 frontend 目录下执行）：
//   node --test src/gitDiffParser.test.mjs   # 只跑本文件
//   node --test                              # 自动发现全部 *.test.mjs
//   node --test "src/**/*.test.mjs"          # 显式 glob
// 注意：不要用 `node --test src/`（目录参数在本 node 版本下不被支持）。
//
// 说明：该解析器当前是 Git diff 的「降级路径」——优先由
// /api/git/file-content 提供两侧全文；仅当全文不可得时才用本解析器
// 把 unified diff 还原成左右两份文本。因此这里覆盖的是解析器本身的
// 纯函数行为，不涉及 DOM / Monaco。
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseUnifiedDiff } from "./gitDiffParser.js";

const EMPTY = {
  oldText: "",
  newText: "",
  isNewFile: false,
  isDeletedFile: false,
};

test("空输入返回空结果", () => {
  assert.deepEqual(parseUnifiedDiff(""), EMPTY);
  assert.deepEqual(parseUnifiedDiff(undefined), EMPTY);
  assert.deepEqual(parseUnifiedDiff(null), EMPTY);
});

test("基本单 hunk 修改：还原左右两份内容", () => {
  const diff = [
    "diff --git a/a.txt b/a.txt",
    "index 111..222 100644",
    "--- a/a.txt",
    "+++ b/a.txt",
    "@@ -1,3 +1,3 @@",
    " ctx1",
    "-old2",
    "+new2",
    " ctx3",
  ].join("\n");
  const r = parseUnifiedDiff(diff);
  assert.equal(r.oldText, "ctx1\nold2\nctx3");
  assert.equal(r.newText, "ctx1\nnew2\nctx3");
  assert.equal(r.isNewFile, false);
  assert.equal(r.isDeletedFile, false);
});

test("新增文件：oldText 为空且 isNewFile=true", () => {
  const diff = [
    "diff --git a/n.txt b/n.txt",
    "new file mode 100644",
    "--- /dev/null",
    "+++ b/n.txt",
    "@@ -0,0 +1,2 @@",
    "+line1",
    "+line2",
  ].join("\n");
  const r = parseUnifiedDiff(diff);
  assert.equal(r.oldText, "");
  assert.equal(r.newText, "line1\nline2");
  assert.equal(r.isNewFile, true);
});

test("删除文件：newText 为空且 isDeletedFile=true", () => {
  const diff = [
    "diff --git a/d.txt b/d.txt",
    "deleted file mode 100644",
    "--- a/d.txt",
    "+++ /dev/null",
    "@@ -1,2 +0,0 @@",
    "-gone1",
    "-gone2",
  ].join("\n");
  const r = parseUnifiedDiff(diff);
  assert.equal(r.oldText, "gone1\ngone2");
  assert.equal(r.newText, "");
  assert.equal(r.isDeletedFile, true);
});

test("单行 hunk（省略 count）", () => {
  const diff = ["--- a/s.txt", "+++ b/s.txt", "@@ -5 +5 @@", "-x", "+y"].join(
    "\n",
  );
  const r = parseUnifiedDiff(diff);
  assert.equal(r.oldText, "x");
  assert.equal(r.newText, "y");
});

test("忽略 \\ No newline at end of file 标记行", () => {
  const diff = [
    "--- a/nl.txt",
    "+++ b/nl.txt",
    "@@ -1 +1 @@",
    "-a",
    "\\ No newline at end of file",
    "+b",
    "\\ No newline at end of file",
  ].join("\n");
  const r = parseUnifiedDiff(diff);
  assert.equal(r.oldText, "a");
  assert.equal(r.newText, "b");
});

test("紧凑模式（默认）：只补 hunk 间相对间隙，不补开头空白", () => {
  // 两个 hunk 相隔：100 - 1 - 1 = 98 行间隙，紧凑模式保留该间隙以维持对齐
  const diff = [
    "--- a/m.txt",
    "+++ b/m.txt",
    "@@ -1,1 +1,1 @@",
    "-a",
    "+A",
    "@@ -100,1 +100,1 @@",
    "-b",
    "+B",
  ].join("\n");
  const r = parseUnifiedDiff(diff);
  const oldLines = r.oldText.split("\n");
  assert.equal(oldLines.length, 100);
  assert.equal(oldLines[0], "a");
  assert.equal(oldLines[50], "");
  assert.equal(oldLines[99], "b");
  assert.equal(r.newText.split("\n")[99], "B");
});

test("紧凑模式：首 hunk 不从第 1 行开始时，不补开头空白行", () => {
  const diff = [
    "--- a/g.txt",
    "+++ b/g.txt",
    "@@ -50,1 +50,1 @@",
    "-p",
    "+P",
  ].join("\n");
  const r = parseUnifiedDiff(diff);
  assert.equal(r.oldText, "p");
  assert.equal(r.newText, "P");
});

test("绝对行号模式：按 diff 中的绝对行号补齐（含开头空白）", () => {
  const diff = [
    "--- a/g.txt",
    "+++ b/g.txt",
    "@@ -50,1 +50,1 @@",
    "-p",
    "+P",
  ].join("\n");
  const r = parseUnifiedDiff(diff, { absoluteLineNumbers: true });
  const oldLines = r.oldText.split("\n");
  assert.equal(oldLines.length, 50);
  assert.equal(oldLines[49], "p");
  assert.equal(r.newText.split("\n")[49], "P");
});

test("绝对行号模式：多 hunk 按绝对行号对齐", () => {
  const diff = [
    "--- a/m.txt",
    "+++ b/m.txt",
    "@@ -1,1 +1,1 @@",
    "-a",
    "+A",
    "@@ -100,1 +100,1 @@",
    "-b",
    "+B",
  ].join("\n");
  const r = parseUnifiedDiff(diff, { absoluteLineNumbers: true });
  assert.equal(r.oldText.split("\n").length, 100);
  assert.equal(r.oldText.split("\n")[0], "a");
  assert.equal(r.oldText.split("\n")[99], "b");
  assert.equal(r.newText.split("\n")[99], "B");
});

test("纯上下文 diff：两侧内容相同", () => {
  const diff = [
    "--- a/c.txt",
    "+++ b/c.txt",
    "@@ -1,2 +1,2 @@",
    " same1",
    " same2",
  ].join("\n");
  const r = parseUnifiedDiff(diff);
  assert.equal(r.oldText, "same1\nsame2");
  assert.equal(r.newText, "same1\nsame2");
});

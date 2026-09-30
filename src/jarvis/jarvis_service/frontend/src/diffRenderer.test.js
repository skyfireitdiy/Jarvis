// diffRenderer 的单元测试（vitest + jsdom）。
//
// 运行方式（在 frontend 目录下执行）：
//   npx vitest run src/diffRenderer.test.js   # 只跑本文件
//   npm run test:vitest                       # 跑全部 vitest 用例
//
// 说明：escapeHtml 依赖 document，故用 vitest 的 jsdom 环境。
// 断言渲染结果的真实 HTML 片段（class / 行号 / 转义），不测内部实现。
import { describe, test, expect, afterEach } from "vitest";
import {
  getLanguageFromFilename,
  escapeHtml,
  renderInlineDiff,
  renderSideBySideDiff,
} from "./diffRenderer.js";

// 构造一行 diff 数据
const row = (type, oldNum, oldLine, newNum, newLine) => ({
  type,
  old_line_num: oldNum,
  old_line: oldLine,
  new_line_num: newNum,
  new_line: newLine,
});

const makeDiff = (rows, extra = {}) => ({
  file_path: "a.py",
  additions: 1,
  deletions: 1,
  rows,
  ...extra,
});

// jsdom 下 window.innerWidth 可写；用例后还原，避免污染其它用例
const originalInnerWidth = window.innerWidth;
afterEach(() => {
  window.innerWidth = originalInnerWidth;
});

describe("getLanguageFromFilename", () => {
  test("空/undefined 返回 plaintext", () => {
    expect(getLanguageFromFilename("")).toBe("plaintext");
    expect(getLanguageFromFilename(undefined)).toBe("plaintext");
    expect(getLanguageFromFilename(null)).toBe("plaintext");
  });

  test("已知扩展名映射正确", () => {
    expect(getLanguageFromFilename("a.py")).toBe("python");
    expect(getLanguageFromFilename("a.js")).toBe("javascript");
    expect(getLanguageFromFilename("a.h")).toBe("cpp");
    expect(getLanguageFromFilename("a.yml")).toBe("yaml");
    expect(getLanguageFromFilename("a.cfg")).toBe("ini");
    expect(getLanguageFromFilename("a.md")).toBe("markdown");
    expect(getLanguageFromFilename("a.txt")).toBe("plaintext");
  });

  test("大小写不敏感", () => {
    expect(getLanguageFromFilename("A.PY")).toBe("python");
    expect(getLanguageFromFilename("A.YML")).toBe("yaml");
  });

  test("多点文件名取最后一段扩展名", () => {
    expect(getLanguageFromFilename("a.test.py")).toBe("python");
    expect(getLanguageFromFilename("/path/to/x.min.js")).toBe("javascript");
  });

  test("无扩展名或未知扩展名返回 plaintext", () => {
    expect(getLanguageFromFilename("Makefile")).toBe("plaintext");
    expect(getLanguageFromFilename("a.unknownext")).toBe("plaintext");
  });
});

describe("escapeHtml", () => {
  test("空值返回空串", () => {
    expect(escapeHtml("")).toBe("");
    expect(escapeHtml(undefined)).toBe("");
    expect(escapeHtml(null)).toBe("");
  });

  test("转义 HTML 特殊字符", () => {
    expect(escapeHtml("<div>")).toBe("&lt;div&gt;");
    expect(escapeHtml("a & b")).toBe("a &amp; b");
    // 双引号在文本节点内不转义（innerHTML 只对属性值转义引号），这是浏览器真实语义
    expect(escapeHtml('"x"')).toBe('"x"');
  });

  test("换行替换为 <br>", () => {
    expect(escapeHtml("a\nb")).toBe("a<br>b");
  });

  test("XSS 载荷被转义，不产生可执行标签", () => {
    const out = escapeHtml("<script>alert(1)</script>");
    expect(out).not.toContain("<script>");
    expect(out).toContain("&lt;script&gt;");
  });
});

describe("renderInlineDiff", () => {
  test("无数据或 rows 缺失时返回占位", () => {
    expect(renderInlineDiff(null)).toContain("diff-error");
    expect(renderInlineDiff({})).toContain("diff-error");
    expect(renderInlineDiff({ rows: null })).toContain("diff-error");
  });

  test("正常渲染含标题、文件路径与统计", () => {
    const html = renderInlineDiff(makeDiff([row("equal", 1, "x", 1, "x")]));
    expect(html).toContain("diff-header");
    expect(html).toContain("diff-file-path");
    expect(html).toContain("a.py");
    expect(html).toContain("diff-stats");
    expect(html).toContain("diff-inline");
  });

  test("delete/insert/equal 的行类型 class 与行号正确", () => {
    const html = renderInlineDiff(
      makeDiff([
        row("delete", 1, "gone", null, null),
        row("insert", null, null, 1, "added"),
        row("equal", 2, "same", 2, "same"),
      ]),
    );
    expect(html).toContain("diff-deleted");
    expect(html).toContain("diff-added");
    // equal 行不带增删背景色
    expect(html).toMatch(/<td class="diff-content ">/);
  });

  test("replace 输出旧行与新行两条", () => {
    const html = renderInlineDiff(
      makeDiff([row("replace", 1, "old", 1, "new")]),
    );
    expect(html).toContain("diff-deleted");
    expect(html).toContain("diff-added");
    expect(html).toContain("old");
    expect(html).toContain("new");
  });

  test("行号不连续时插入分界线", () => {
    const html = renderInlineDiff(
      makeDiff([
        row("equal", 1, "a", 1, "a"),
        row("equal", 10, "b", 10, "b"), // 行号跳跃
      ]),
    );
    expect(html).toContain("diff-separator");
  });

  test("行号连续时不插入分界线", () => {
    const html = renderInlineDiff(
      makeDiff([row("equal", 1, "a", 1, "a"), row("equal", 2, "b", 2, "b")]),
    );
    expect(html).not.toContain("diff-separator");
  });

  test("file_path 缺失时显示 Unknown", () => {
    const html = renderInlineDiff(
      makeDiff([row("equal", 1, "a", 1, "a")], { file_path: "" }),
    );
    expect(html).toContain("Unknown");
  });

  test("未知语言时降级为纯文本且不抛错", () => {
    const html = renderInlineDiff(
      makeDiff([row("equal", 1, "  indented", 1, "  indented")], {
        file_path: "a.unknownext",
      }),
    );
    expect(html).toContain("indented");
  });
});

describe("renderSideBySideDiff", () => {
  test("无数据时返回占位", () => {
    expect(renderSideBySideDiff(null)).toContain("diff-error");
    expect(renderSideBySideDiff({})).toContain("diff-error");
  });

  test("非移动端渲染 4 列并排结构", () => {
    window.innerWidth = 1024;
    const html = renderSideBySideDiff(
      makeDiff([row("replace", 1, "old", 1, "new")]),
    );
    expect(html).toContain("diff-side-by-side");
    expect(html).toContain("<colgroup><col><col><col><col></colgroup>");
    expect(html).toContain("diff-old-num");
    expect(html).toContain("diff-new-num");
  });

  test("移动端（<=768）降级为内联渲染", () => {
    window.innerWidth = 768;
    const html = renderSideBySideDiff(
      makeDiff([row("replace", 1, "old", 1, "new")]),
    );
    expect(html).toContain("diff-inline");
    expect(html).not.toContain("<colgroup><col><col><col><col></colgroup>");
  });

  test("delete 行只填旧列，insert 行只填新列", () => {
    window.innerWidth = 1024;
    const html = renderSideBySideDiff(
      makeDiff([
        row("delete", 1, "gone", null, null),
        row("insert", null, null, 1, "added"),
      ]),
    );
    expect(html).toContain("diff-row-delete");
    expect(html).toContain("diff-row-insert");
    expect(html).toContain("gone");
    expect(html).toContain("added");
  });

  test("行号跳跃时插入 4 列分界线", () => {
    window.innerWidth = 1024;
    const html = renderSideBySideDiff(
      makeDiff([row("equal", 1, "a", 1, "a"), row("equal", 20, "b", 20, "b")]),
    );
    expect(html).toContain(
      '<tr class="diff-separator"><td colspan="4"></td></tr>',
    );
  });
});

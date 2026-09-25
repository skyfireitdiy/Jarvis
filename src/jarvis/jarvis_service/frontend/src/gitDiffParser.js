// unified diff 解析：把 `git show` 产生的标准 unified diff 文本拆成
// 「旧文件内容 / 新文件内容」两份文本，供 Monaco DiffEditor 的
// original / modified 两个 model 使用。
//
// 之所以需要它：Monaco 的 DiffEditor 不做 diff 计算，它只负责「展示」
// 两份文本的差异。因此必须先把 unified diff 还原成左右两份完整文本。
//
// 设计要点：
// - 纯函数，无副作用、无依赖，便于用 node 直接单测。
// - hunk 之间行号不连续时用空行补齐，保证左右两侧行号对齐，
//   否则 Monaco 会把后续内容整体错位（这是最容易踩的坑）。
// - 新增文件（--- /dev/null）oldText 为空；删除文件（+++ /dev/null）newText 为空。

/**
 * 解析 unified diff 文本为左右两份内容。
 *
 * 注意：后端 `git show --format=` 返回的是**局部 diff**（只含变更区域及其上下文），
 * 不含文件全文。因此默认采用「紧凑模式」：不把内容补齐到 diff 里的绝对行号，
 * 仅保留各 hunk 自身内容与 hunk 之间的相对间隙。否则 Monaco 会在变更内容前
 * 渲染出成千上万行空白，体验极差。
 *
 * @param {string} diffText - `git show`/`git diff` 输出的 unified diff 文本
 * @param {{ absoluteLineNumbers?: boolean }} [options]
 *        absoluteLineNumbers=true 时按 diff 中的绝对行号补齐（适用于
 *        左右两侧本就提供完整文件全文的场景）；默认 false（紧凑模式）。
 * @returns {{ oldText: string, newText: string, isNewFile: boolean, isDeletedFile: boolean }}
 */
export function parseUnifiedDiff(diffText, options = {}) {
  const empty = {
    oldText: "",
    newText: "",
    isNewFile: false,
    isDeletedFile: false,
  };
  if (!diffText || typeof diffText !== "string") return empty;
  const absoluteLineNumbers = options.absoluteLineNumbers === true;

  const lines = diffText.split("\n");
  const oldLines = [];
  const newLines = [];

  let isNewFile = false;
  let isDeletedFile = false;
  // 是否已进入 hunk 主体（头部行与 hunk 行要区别对待）
  let inHunk = false;
  // 当前 hunk 剩余应消费的旧/新行数（用于 hunk 结束后补齐）
  let oldRemaining = 0;
  let newRemaining = 0;
  // 当前 hunk 已写入的旧/新行数
  let oldWritten = 0;
  let newWritten = 0;
  // 已写入的旧/新行数总量，用于 hunk 之间按行号补齐对齐
  let oldTotal = 0;
  let newTotal = 0;
  // 上一个 hunk 的起始行号与行数（紧凑模式下用于计算 hunk 间相对间隙）
  let lastHunkOldStart = null;
  let lastHunkNewStart = null;
  let lastHunkOldCount = 0;
  let lastHunkNewCount = 0;

  // 一个 hunk 收尾：若声明的行数没消费完（diff 被截断等），补空行保持对齐
  const closeHunk = () => {
    if (!inHunk) return;
    while (oldWritten < oldRemaining) {
      oldLines.push("");
      oldWritten += 1;
      oldTotal += 1;
    }
    while (newWritten < newRemaining) {
      newLines.push("");
      newWritten += 1;
      newTotal += 1;
    }
    inHunk = false;
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];

    // 文件头：diff --git / index / old mode / new mode / similarity 等
    if (line.startsWith("diff --git ")) {
      closeHunk();
      continue;
    }
    if (
      line.startsWith("index ") ||
      line.startsWith("old mode ") ||
      line.startsWith("new mode ")
    ) {
      continue;
    }
    if (
      line.startsWith("similarity index ") ||
      line.startsWith("dissimilarity index ")
    ) {
      continue;
    }
    if (line.startsWith("rename from ") || line.startsWith("rename to ")) {
      continue;
    }
    if (line.startsWith("new file mode ")) {
      isNewFile = true;
      continue;
    }
    if (line.startsWith("deleted file mode ")) {
      isDeletedFile = true;
      continue;
    }

    // --- / +++ 头部：标记新增/删除文件，但不作为内容
    if (line.startsWith("--- ")) {
      if (line.slice(4).trim() === "/dev/null") isNewFile = true;
      continue;
    }
    if (line.startsWith("+++ ")) {
      if (line.slice(4).trim() === "/dev/null") isDeletedFile = true;
      continue;
    }

    // hunk 头：@@ -oldStart,oldCount +newStart,newCount @@
    if (line.startsWith("@@")) {
      closeHunk();
      const match = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(line);
      if (match) {
        const oldStart = Number(match[1]);
        const newStart = Number(match[3]);
        oldRemaining = match[2] === undefined ? 1 : Number(match[2]);
        newRemaining = match[4] === undefined ? 1 : Number(match[4]);
        // hunk 之间行号不连续时补空行，保证左右两侧行号对齐，
        // 否则 Monaco 会把后续差异整体错位。
        // - 绝对模式：补到 diff 里的绝对行号（oldStart-1）。
        // - 紧凑模式（默认）：只补 hunk 之间的相对间隙，避免局部 diff
        //   在内容前产生大量空白行。
        if (absoluteLineNumbers) {
          while (oldTotal < oldStart - 1) {
            oldLines.push("");
            oldTotal += 1;
          }
          while (newTotal < newStart - 1) {
            newLines.push("");
            newTotal += 1;
          }
        } else if (lastHunkOldStart !== null) {
          const oldGap = oldStart - lastHunkOldStart - lastHunkOldCount;
          const newGap = newStart - lastHunkNewStart - lastHunkNewCount;
          for (let g = 0; g < oldGap; g += 1) {
            oldLines.push("");
            oldTotal += 1;
          }
          for (let g = 0; g < newGap; g += 1) {
            newLines.push("");
            newTotal += 1;
          }
        }
        lastHunkOldStart = oldStart;
        lastHunkNewStart = newStart;
        lastHunkOldCount = oldRemaining;
        lastHunkNewCount = newRemaining;
        oldWritten = 0;
        newWritten = 0;
        inHunk = true;
      }
      continue;
    }

    // "\ No newline at end of file"：忽略
    if (line.startsWith("\\")) continue;

    if (!inHunk) continue;

    const marker = line.charAt(0);
    const content = line.slice(1);

    if (marker === " ") {
      // 上下文行：两侧都要
      oldLines.push(content);
      newLines.push(content);
      oldWritten += 1;
      newWritten += 1;
      oldTotal += 1;
      newTotal += 1;
    } else if (marker === "-") {
      oldLines.push(content);
      oldWritten += 1;
      oldTotal += 1;
    } else if (marker === "+") {
      newLines.push(content);
      newWritten += 1;
      newTotal += 1;
    } else if (line === "") {
      // 某些实现下空行会丢掉前缀，按上下文空行处理
      oldLines.push("");
      newLines.push("");
      oldWritten += 1;
      newWritten += 1;
      oldTotal += 1;
      newTotal += 1;
    }
  }

  closeHunk();

  // 去掉 split('\n') 因末尾换行产生的多余空行，避免两侧各多一行
  if (oldLines.length && oldLines[oldLines.length - 1] === "") oldLines.pop();
  if (newLines.length && newLines[newLines.length - 1] === "") newLines.pop();

  return {
    oldText: oldLines.join("\n"),
    newText: newLines.join("\n"),
    isNewFile,
    isDeletedFile,
  };
}

/**
 * 从 unified diff 中提取「变更上下文区域」：只保留各 hunk 的内容
 * （上下文行 + 增删行），丢弃 hunk 之间的文件头与未变更的大段代码。
 *
 * 与 parseUnifiedDiff 的区别：parseUnifiedDiff 会为 hunk 之间的行号间隙
 * 补空行以对齐绝对行号，从而在全文模式下产生大段空白；本函数只取 hunk
 * 主体，因此左右两侧文本紧凑，适合「只显示 diff 上下文」的阅读模式。
 *
 * @param {string} diffText - `git show`/`git diff` 输出的 unified diff 文本
 * @returns {{ oldText: string, newText: string, isNewFile: boolean, isDeletedFile: boolean }}
 */
export function extractDiffContext(diffText) {
  const empty = {
    oldText: "",
    newText: "",
    isNewFile: false,
    isDeletedFile: false,
  };
  if (!diffText || typeof diffText !== "string") return empty;

  const lines = diffText.split("\n");
  const oldLines = [];
  const newLines = [];

  let isNewFile = false;
  let isDeletedFile = false;
  let inHunk = false;
  let oldRemaining = 0;
  let newRemaining = 0;
  let oldWritten = 0;
  let newWritten = 0;

  // hunk 收尾：diff 被截断导致行数不足时补空行，保持左右对齐
  const closeHunk = () => {
    if (!inHunk) return;
    while (oldWritten < oldRemaining) {
      oldLines.push("");
      oldWritten += 1;
    }
    while (newWritten < newRemaining) {
      newLines.push("");
      newWritten += 1;
    }
    inHunk = false;
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];

    if (line.startsWith("new file mode ")) {
      isNewFile = true;
      continue;
    }
    if (line.startsWith("deleted file mode ")) {
      isDeletedFile = true;
      continue;
    }
    if (line.startsWith("--- ")) {
      if (line.slice(4).trim() === "/dev/null") isNewFile = true;
      continue;
    }
    if (line.startsWith("+++ ")) {
      if (line.slice(4).trim() === "/dev/null") isDeletedFile = true;
      continue;
    }

    if (line.startsWith("@@")) {
      closeHunk();
      const match = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(line);
      if (match) {
        oldRemaining = match[2] === undefined ? 1 : Number(match[2]);
        newRemaining = match[4] === undefined ? 1 : Number(match[4]);
        oldWritten = 0;
        newWritten = 0;
        inHunk = true;
      }
      continue;
    }

    // "\ No newline at end of file"：忽略
    if (line.startsWith("\\")) continue;

    if (!inHunk) continue;

    const marker = line.charAt(0);
    const content = line.slice(1);

    if (marker === " ") {
      oldLines.push(content);
      newLines.push(content);
      oldWritten += 1;
      newWritten += 1;
    } else if (marker === "-") {
      oldLines.push(content);
      oldWritten += 1;
    } else if (marker === "+") {
      newLines.push(content);
      newWritten += 1;
    } else if (line === "") {
      oldLines.push("");
      newLines.push("");
      oldWritten += 1;
      newWritten += 1;
    }
  }

  closeHunk();

  if (oldLines.length && oldLines[oldLines.length - 1] === "") oldLines.pop();
  if (newLines.length && newLines[newLines.length - 1] === "") newLines.pop();

  return {
    oldText: oldLines.join("\n"),
    newText: newLines.join("\n"),
    isNewFile,
    isDeletedFile,
  };
}

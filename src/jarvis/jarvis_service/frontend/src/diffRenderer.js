import hljs from "highlight.js";

// 语言映射表
const langMap = {
  py: "python",
  js: "javascript",
  ts: "typescript",
  vue: "vue",
  java: "java",
  c: "c",
  cpp: "cpp",
  h: "cpp",
  hpp: "cpp",
  go: "go",
  rs: "rust",
  rb: "ruby",
  php: "php",
  swift: "swift",
  kt: "kotlin",
  scala: "scala",
  sql: "sql",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  yaml: "yaml",
  yml: "yaml",
  json: "json",
  toml: "toml",
  ini: "ini",
  cfg: "ini",
  conf: "ini",
  xml: "xml",
  html: "html",
  css: "css",
  scss: "scss",
  less: "less",
  md: "markdown",
  txt: "plaintext",
  log: "plaintext",
};

/**
 * 根据文件名获取语言类型
 * @param {string} filename - 文件名
 * @returns {string} 语言类型
 */
export function getLanguageFromFilename(filename) {
  if (!filename) return "plaintext";
  const ext = filename.split(".").pop().toLowerCase();
  return langMap[ext] || "plaintext";
}

/**
 * HTML转义
 * @param {string} text - 需要转义的文本
 * @returns {string} 转义后的HTML
 */
export function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML.replace(/\n/g, "<br>");
}

/**
 * 当前是否处于移动端视口（与全局断点保持一致：<= 768px）
 * @returns {boolean}
 */
function isMobileViewport() {
  return typeof window !== "undefined" && window.innerWidth <= 768;
}

/**
 * 渲染单行内容（保留缩进 + 语法高亮，失败降级纯文本）
 * @param {string} line - 行内容
 * @param {string} language - 语言类型
 * @returns {string} 渲染后的 HTML 片段
 */
function renderLineContent(line, language) {
  if (line === null || line === undefined) return "";
  const leadingSpaces = line.match(/^(\s*)/)[0];
  try {
    const highlighted = hljs.highlight(line, { language }).value;
    return (
      "&nbsp;".repeat(leadingSpaces.length) + highlighted.replace(/^(\s+)/, "")
    );
  } catch (e) {
    // 如果语法高亮不支持该语言，降级为纯文本显示
    console.warn("[highlight.js] Language not supported:", language, e);
    return "&nbsp;".repeat(leadingSpaces.length) + escapeHtml(line);
  }
}

/**
 * 渲染移动端内联 diff（单列，不并排）
 *
 * 行映射规则（保证信息不丢失）：
 * - equal：显示新行号 + 新内容
 * - delete：显示旧行号 + 旧内容（红底）
 * - insert：显示新行号 + 新内容（绿底）
 * - replace：先输出一行旧内容（红底），再输出一行新内容（绿底）
 *
 * @param {Object} diffData - diff数据对象
 * @returns {string} 渲染后的HTML
 */
export function renderInlineDiff(diffData) {
  if (!diffData || !diffData.rows) {
    return '<div class="diff-error">No diff data</div>';
  }

  const { file_path, additions, deletions, rows } = diffData;
  const language = getLanguageFromFilename(file_path);

  let html = '<div class="diff-side-by-side diff-inline">';

  // 标题
  html += '<div class="diff-header">';
  html += `<span class="diff-file-path">📝 ${escapeHtml(file_path || "Unknown")}</span>`;
  html += `<span class="diff-stats">[<span class="diff-additions">+${additions}</span> / <span class="diff-deletions">-${deletions}</span>]</span>`;
  html += "</div>";

  html += '<table class="diff-table">';
  html += "<colgroup><col><col></colgroup>";

  let lastOldLineNum = 0;
  let lastNewLineNum = 0;

  const appendSeparator = () => {
    html += '<tr class="diff-separator"><td colspan="2"></td></tr>';
  };

  const appendLine = (lineNum, content, contentClass) => {
    html += '<tr class="diff-row">';
    html += `<td class="diff-line-num">${escapeHtml(String(lineNum || ""))}</td>`;
    html += `<td class="diff-content ${contentClass}"><code>${content}</code></td>`;
    html += "</tr>";
  };

  rows.forEach((row, index) => {
    const { type, old_line_num, old_line, new_line_num, new_line } = row;

    // 行号不连续时插入分界线（与并排渲染保持一致）
    if (index > 0) {
      const isOldLineGap =
        old_line_num && lastOldLineNum && old_line_num - lastOldLineNum > 1;
      const isNewLineGap =
        new_line_num && lastNewLineNum && new_line_num - lastNewLineNum > 1;
      if (isOldLineGap || isNewLineGap) {
        appendSeparator();
      }
    }

    if (old_line_num) lastOldLineNum = old_line_num;
    if (new_line_num) lastNewLineNum = new_line_num;

    if (type === "delete") {
      appendLine(
        old_line_num,
        renderLineContent(old_line, language),
        "diff-deleted",
      );
      return;
    }

    if (type === "insert") {
      appendLine(
        new_line_num,
        renderLineContent(new_line, language),
        "diff-added",
      );
      return;
    }

    if (type === "replace") {
      // 替换行：先旧后新，各自独立一行，避免并排挤压
      appendLine(
        old_line_num,
        renderLineContent(old_line, language),
        "diff-deleted",
      );
      appendLine(
        new_line_num,
        renderLineContent(new_line, language),
        "diff-added",
      );
      return;
    }

    // equal：显示新行号 + 新内容
    appendLine(new_line_num, renderLineContent(new_line, language), "");
  });

  html += "</table>";
  html += "</div>";

  return html;
}

/**
 * 渲染side-by-side diff
 * @param {Object} diffData - diff数据对象
 * @returns {string} 渲染后的HTML
 */
export function renderSideBySideDiff(diffData) {
  if (!diffData || !diffData.rows) {
    return '<div class="diff-error">No diff data</div>';
  }

  // 移动端屏幕窄，并排两列每列仅百余像素不可读，改用单列内联渲染
  if (isMobileViewport()) {
    return renderInlineDiff(diffData);
  }

  const { file_path, additions, deletions, rows } = diffData;
  const language = getLanguageFromFilename(file_path);

  let html = '<div class="diff-side-by-side">';

  // 标题
  html += '<div class="diff-header">';
  html += `<span class="diff-file-path">📝 ${escapeHtml(file_path || "Unknown")}</span>`;
  html += `<span class="diff-stats">[<span class="diff-additions">+${additions}</span> / <span class="diff-deletions">-${deletions}</span>]</span>`;
  html += "</div>";

  // 表格
  html += '<table class="diff-table">';
  html += "<colgroup><col><col><col><col></colgroup>";

  let lastOldLineNum = 0;
  let lastNewLineNum = 0;

  rows.forEach((row, index) => {
    const { type, old_line_num, old_line, new_line_num, new_line } = row;

    // 检查是否需要插入分界线（行号不连续）
    // 注意：第一行不检查，且只在行号有效时检查
    if (index > 0) {
      const isOldLineGap =
        old_line_num && lastOldLineNum && old_line_num - lastOldLineNum > 1;
      const isNewLineGap =
        new_line_num && lastNewLineNum && new_line_num - lastNewLineNum > 1;

      // 如果任一侧出现跳跃，且该侧有行号，则插入分界线
      // 或者如果两侧都有行号，但只有一侧跳跃（例如只改了一侧），也插入分界线
      if (isOldLineGap || isNewLineGap) {
        html += '<tr class="diff-separator"><td colspan="4"></td></tr>';
      }
    }

    // 更新上一次的行号
    if (old_line_num) lastOldLineNum = old_line_num;
    if (new_line_num) lastNewLineNum = new_line_num;

    // 行背景色类
    let rowClass = "diff-row diff-row-" + type;

    // 开始表格行
    html += `<tr class="${rowClass}">`;

    // 旧代码列
    if (type === "equal" || type === "delete" || type === "replace") {
      html += `<td class="diff-line-num diff-old-num">${escapeHtml(String(old_line_num || ""))}</td>`;

      // 统计并保留缩进
      let oldContent = "";
      if (old_line) {
        const leadingSpaces = old_line.match(/^(\s*)/)[0];
        let highlighted;
        try {
          highlighted = hljs.highlight(old_line, { language }).value;
          // 在高亮结果前添加显式的 &nbsp; 来保留缩进
          oldContent =
            "&nbsp;".repeat(leadingSpaces.length) +
            highlighted.replace(/^(\s+)/, "");
        } catch (e) {
          // 如果语法高亮不支持该语言，降级为纯文本显示
          console.warn("[highlight.js] Language not supported:", language, e);
          oldContent =
            "&nbsp;".repeat(leadingSpaces.length) + escapeHtml(old_line);
        }
      }

      // 对于 replace 和 delete，添加删除背景色到 td
      const oldClass =
        type === "replace" || type === "delete" ? "diff-deleted" : "";
      html += `<td class="diff-content diff-old-content ${oldClass}"><code>${oldContent}</code></td>`;
    } else {
      html += '<td class="diff-line-num diff-old-num"></td>';
      html += '<td class="diff-content diff-old-content"></td>';
    }

    // 新代码列
    if (type === "equal" || type === "insert" || type === "replace") {
      html += `<td class="diff-line-num diff-new-num">${escapeHtml(String(new_line_num || ""))}</td>`;

      // 统计并保留缩进
      let newContent = "";
      if (new_line !== null && new_line !== undefined) {
        // 即使是空字符串也要处理，确保显示占位符
        const leadingSpaces = new_line.match(/^(\s*)/)[0];
        let highlighted;
        try {
          highlighted = hljs.highlight(new_line, { language }).value;
          // 在高亮结果前添加显式的 &nbsp; 来保留缩进
          newContent =
            "&nbsp;".repeat(leadingSpaces.length) +
            highlighted.replace(/^(\s+)/, "");
        } catch (e) {
          // 如果语法高亮不支持该语言，降级为纯文本显示
          console.warn("[highlight.js] Language not supported:", language, e);
          newContent =
            "&nbsp;".repeat(leadingSpaces.length) + escapeHtml(new_line);
        }
        // 如果内容为空，添加一个空格占位符
        if (!newContent) {
          newContent = "&nbsp;";
        }
      } else {
        // new_line 为 null 或 undefined 时，显示空占位符
        newContent = "";
      }

      // 对于 replace 和 insert，添加新增背景色到 td
      const newClass =
        type === "replace" || type === "insert" ? "diff-added" : "";
      html += `<td class="diff-content diff-new-content ${newClass}"><code>${newContent}</code></td>`;
    } else {
      html += '<td class="diff-line-num diff-new-num"></td>';
      html += '<td class="diff-content diff-new-content"></td>';
    }

    html += "</tr>";
  });

  html += "</table>";
  html += "</div>";

  return html;
}

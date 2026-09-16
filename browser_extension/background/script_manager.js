// 脚本仓库（类油猴）：管理用户安装的自定义页面脚本。
//
// 脚本定位：一段可在页面「主世界」执行的 JS，求值后应得到一个脚本对象：
//   {
//     name: "mysite",
//     description: "某站点文档操作",
//     version: "1.0.0",
//     match: ["example.com"],           // 适用域名（仅作提示，不做强制拦截）
//     actions: {
//       getEditor: { desc: "获取编辑器实例", run: () => {...} },
//       deleteRange: { desc: "删除文本", params: {start:"number",end:"number"},
//                      run: ({start,end}) => {...} },
//     },
//   }
//
// 兼容两种导出写法：
//   (a) 顶层定义变量后 `module.exports = {...}` 或 `globalThis.__JARVIS_SCRIPT__ = {...}`；
//   (b) 直接 `globalThis.__JARVIS_SCRIPT__ = {...}`。
//
// 本模块只负责「存取 + 轻量静态校验」，不执行任何脚本（执行见 script_executor.js）。

import { cmdError } from "./command_router.js";

/** chrome.storage.local 中存放脚本列表的键名。 */
const STORAGE_KEY = "scripts";

export class ScriptManager {
  /**
   * 列出已安装脚本的元数据（不含 source，避免响应过大）。
   * @returns {Promise<Array<object>>}
   */
  async list() {
    const scripts = await this._load();
    return scripts.map((s) => this._toMeta(s));
  }

  /**
   * 读取单个脚本（含 source）。
   * @param {string} id 脚本 ID
   * @returns {Promise<object>} 完整脚本对象
   */
  async get(id) {
    if (!id) throw cmdError("SCRIPT_INVALID", "id is required");
    const scripts = await this._load();
    const found = scripts.find((s) => s.id === id);
    if (!found) throw cmdError("SCRIPT_NOT_FOUND", `script not found: ${id}`);
    return found;
  }

  /**
   * 安装（或更新）脚本。同名脚本已存在时覆盖，保留原 id 与 installed_at。
   * @param {object} payload { name, source, description, match, version }
   * @returns {Promise<object>} 安装后的脚本元数据
   */
  async install({ name, source, description, match, version }) {
    const scriptName = String(name || "").trim();
    if (!scriptName) {
      throw cmdError("SCRIPT_INVALID", "name is required");
    }
    const src = typeof source === "string" ? source : "";
    if (!src.trim()) {
      throw cmdError("SCRIPT_INVALID", "source is required");
    }
    const reason = validateSource(src);
    if (reason) {
      throw cmdError("SCRIPT_INVALID", reason);
    }

    const scripts = await this._load();
    const idx = scripts.findIndex((s) => s.name === scriptName);
    const now = new Date().toISOString();
    const record = {
      id: idx >= 0 ? scripts[idx].id : genId(),
      name: scriptName,
      description: String(description || "").trim(),
      match: normalizeMatch(match),
      version: String(version || "0.0.0").trim(),
      enabled: idx >= 0 ? scripts[idx].enabled !== false : true,
      installed_at: idx >= 0 ? scripts[idx].installed_at : now,
      updated_at: now,
      source: src,
    };

    if (idx >= 0) {
      scripts[idx] = record;
    } else {
      scripts.push(record);
    }
    await this._save(scripts);
    return this._toMeta(record);
  }

  /**
   * 导出脚本为可分享的独立文件内容。
   *
   * 产出的文本可直接保存为 `.js` 文件分发给他人，对方用「从本地文件导入」
   * 或粘贴到源码框即可安装（与安装入口的格式完全一致）。
   *
   * 文件结构：顶部为元信息注释块（供人阅读），其后是原始脚本源码。
   * 注释块使用 `//` 行注释，不影响脚本求值。
   *
   * @param {string} id 脚本 ID
   * @returns {Promise<object>} { filename, name, version, content }
   */
  async exportScript(id) {
    const script = await this.get(id);
    const name = String(script.name || "script").trim() || "script";
    const version = String(script.version || "0.0.0").trim();
    const description = String(script.description || "").trim();
    const match = Array.isArray(script.match) ? script.match : [];

    const headerLines = [
      "// ===== Jarvis 脚本导出 =====",
      `// name: ${name}`,
      `// version: ${version}`,
    ];
    if (description) headerLines.push(`// description: ${description}`);
    if (match.length) headerLines.push(`// match: ${match.join(", ")}`);
    if (script.updated_at)
      headerLines.push(`// exported_at: ${new Date().toISOString()}`);
    headerLines.push(
      "// 安装方式：扩展 popup →「脚本管理」→ 粘贴本文件内容或从本地文件导入。",
    );
    headerLines.push("// ===========================");

    const content =
      headerLines.join("\n") + "\n\n" + String(script.source || "");
    return {
      filename: `${name}.js`,
      name,
      version,
      content,
    };
  }

  /**
   * 卸载脚本。
   * @param {string} id 脚本 ID
   * @returns {Promise<object>} { ok: true, id }
   */
  async uninstall(id) {
    if (!id) throw cmdError("SCRIPT_INVALID", "id is required");
    const scripts = await this._load();
    const next = scripts.filter((s) => s.id !== id);
    if (next.length === scripts.length) {
      throw cmdError("SCRIPT_NOT_FOUND", `script not found: ${id}`);
    }
    await this._save(next);
    return { ok: true, id };
  }

  /**
   * 启用 / 停用脚本。
   * @param {string} id 脚本 ID
   * @param {boolean} enabled 是否启用
   * @returns {Promise<object>} 更新后的脚本元数据
   */
  async setEnabled(id, enabled) {
    if (!id) throw cmdError("SCRIPT_INVALID", "id is required");
    const scripts = await this._load();
    const found = scripts.find((s) => s.id === id);
    if (!found) throw cmdError("SCRIPT_NOT_FOUND", `script not found: ${id}`);
    found.enabled = enabled !== false;
    found.updated_at = new Date().toISOString();
    await this._save(scripts);
    return this._toMeta(found);
  }

  // ---------------- 内部工具 ----------------

  /** 读取脚本列表；存储损坏时返回空数组。 */
  async _load() {
    const cfg = await chrome.storage.local.get([STORAGE_KEY]);
    const list = cfg[STORAGE_KEY];
    return Array.isArray(list) ? list : [];
  }

  /** 写回脚本列表。 */
  async _save(list) {
    await chrome.storage.local.set({ [STORAGE_KEY]: list });
  }

  /** 转成元数据（剔除 source，保留 source_size）。 */
  _toMeta(s) {
    return {
      id: s.id,
      name: s.name,
      description: s.description || "",
      match: Array.isArray(s.match) ? s.match : [],
      version: s.version || "0.0.0",
      enabled: s.enabled !== false,
      installed_at: s.installed_at || null,
      updated_at: s.updated_at || null,
      source_size: typeof s.source === "string" ? s.source.length : 0,
    };
  }
}

/**
 * 轻量静态校验脚本源码。
 *
 * 注意：这里**不能**用 `new Function(src)` 做语法解析。
 * MV3 扩展页面（popup / service worker）的 CSP 为 `script-src 'self'`，
 * 不允许 `unsafe-eval`，`new Function` 会直接抛 CSP 错误，
 * 导致所有合法脚本都被误判为「syntax error」而无法安装。
 * 因此只做纯字符串层面的静态检查；真正的语法错误会在 `script.run`
 * 于页面主世界求值时暴露（runScriptFn 有 try/catch 兜底）。
 *
 * @param {string} source 脚本源码
 * @returns {string|null} 错误原因；通过时返回 null
 */
export function validateSource(source) {
  const src = String(source);
  // 1) 必须导出脚本对象
  if (!src.includes("__JARVIS_SCRIPT__") && !src.includes("module.exports")) {
    return "script must export an object via globalThis.__JARVIS_SCRIPT__ or module.exports";
  }
  // 2) 必须定义 actions
  if (!/\bactions\b/.test(src)) {
    return "script must define an 'actions' map";
  }
  // 3) 基础括号配平检查（廉价地拦截明显的截断/残缺源码）
  const reason = checkBalanced(src);
  if (reason) return reason;
  return null;
}

/**
 * 括号配平检查：忽略字符串、模板串、注释与正则字面量中的括号。
 * 只做粗粒度判断，用于拦截明显残缺的源码，不追求完备的语法分析。
 * @param {string} src 源码
 * @returns {string|null} 错误原因；通过时返回 null
 */
function checkBalanced(src) {
  const pairs = { ")": "(", "]": "[", "}": "{" };
  const stack = [];
  let i = 0;
  let prevSignificant = ""; // 上一个有效字符，用于区分除号与正则字面量
  while (i < src.length) {
    const c = src[i];
    // 行注释
    if (c === "/" && src[i + 1] === "/") {
      const nl = src.indexOf("\n", i);
      i = nl === -1 ? src.length : nl + 1;
      continue;
    }
    // 块注释
    if (c === "/" && src[i + 1] === "*") {
      const end = src.indexOf("*/", i + 2);
      i = end === -1 ? src.length : end + 2;
      continue;
    }
    // 字符串 / 模板串
    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      i++;
      while (i < src.length) {
        if (src[i] === "\\") {
          i += 2;
          continue;
        }
        if (src[i] === quote) break;
        i++;
      }
      if (i >= src.length) return "unterminated string literal";
      i++;
      prevSignificant = quote;
      continue;
    }
    // 正则字面量（粗判：前面是运算符/开头时视为正则）
    if (c === "/" && /(^|[=(,:[!&|?{};+\-*%<>~^])\s*$/.test(src.slice(0, i))) {
      i++;
      let inClass = false;
      while (i < src.length) {
        if (src[i] === "\\") {
          i += 2;
          continue;
        }
        if (src[i] === "[") inClass = true;
        else if (src[i] === "]") inClass = false;
        else if (src[i] === "/" && !inClass) break;
        else if (src[i] === "\n") return "unterminated regular expression";
        i++;
      }
      i++;
      prevSignificant = "/";
      continue;
    }
    if (c === "(" || c === "[" || c === "{") {
      stack.push(c);
      prevSignificant = c;
      i++;
      continue;
    }
    if (c === ")" || c === "]" || c === "}") {
      if (stack.pop() !== pairs[c]) {
        return `unbalanced '${c}' in script source`;
      }
      prevSignificant = c;
      i++;
      continue;
    }
    if (!/\s/.test(c)) prevSignificant = c;
    i++;
  }
  if (stack.length) {
    return `unclosed '${stack[stack.length - 1]}' in script source`;
  }
  return null;
}

/** 规范化 match 字段为字符串数组。 */
function normalizeMatch(match) {
  if (Array.isArray(match)) {
    return match.map((m) => String(m).trim()).filter(Boolean);
  }
  if (typeof match === "string" && match.trim()) {
    return match
      .split(",")
      .map((m) => m.trim())
      .filter(Boolean);
  }
  return [];
}

/** 生成脚本 ID（参考 service_worker.js 的 getClientId 写法）。 */
function genId() {
  return "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

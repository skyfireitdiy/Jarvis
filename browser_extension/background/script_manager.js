// 脚本仓库（类油猴）：管理用户安装的自定义页面脚本。
//
// 脚本定位：一段可在页面「主世界」执行的 JS，求值后应得到一个脚本对象：
//   {
//     name: "icenter",
//     description: "iCenter wiki 文档操作",
//     version: "1.0.0",
//     match: ["i.zte.com.cn"],          // 适用域名（仅作提示，不做强制拦截）
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
 * 只做语法解析（不执行）与关键字检查，避免在安装阶段运行不可信代码。
 * @param {string} source 脚本源码
 * @returns {string|null} 错误原因；通过时返回 null
 */
export function validateSource(source) {
  const src = String(source);
  // 1) 语法解析：仅解析不执行，语法错误会抛异常
  try {
    // eslint-disable-next-line no-new-func
    new Function(src);
  } catch (e) {
    const msg = e && e.message ? e.message : String(e);
    return `syntax error: ${msg}`;
  }
  // 2) 必须导出脚本对象
  if (!src.includes("__JARVIS_SCRIPT__") && !src.includes("module.exports")) {
    return "script must export an object via globalThis.__JARVIS_SCRIPT__ or module.exports";
  }
  // 3) 必须定义 actions
  if (!/\bactions\b/.test(src)) {
    return "script must define an 'actions' map";
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

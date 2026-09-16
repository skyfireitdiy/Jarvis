// 脚本执行器：管理已安装脚本（类油猴），并在页面「主世界」执行脚本的指定 action。
//
// 两类职责：
// 1. 元数据类（list/get/install/uninstall/setEnabled）—— 直接转发给 ScriptManager；
// 2. 执行类（run）—— 取出脚本源码，通过 chrome.scripting.executeScript({ world: "MAIN" })
//    注入页面执行，从而能访问页面自身的 JS 对象（如站点自带的编辑器实例）。
//
// 注意：注入函数 runScriptFn 必须自包含（不能引用本模块作用域内的任何变量）。

import { cmdError } from "../command_router.js";
import { ScriptManager } from "../script_manager.js";

export class ScriptExecutor {
  constructor() {
    this.manager = new ScriptManager();
  }

  /** 列出已安装脚本的元数据。 */
  async list() {
    return this.manager.list();
  }

  /** 读取单个脚本（含 source）。 */
  async get({ id }) {
    return this.manager.get(id);
  }

  /** 安装（或更新）脚本。 */
  async install({ name, source, description, match, version }) {
    return this.manager.install({ name, source, description, match, version });
  }

  /** 卸载脚本。 */
  async uninstall({ id }) {
    return this.manager.uninstall(id);
  }

  /** 导出脚本为可分享的独立文件内容。 */
  async exportScript({ id }) {
    return this.manager.exportScript(id);
  }

  /** 启用 / 停用脚本。 */
  async setEnabled({ id, enabled }) {
    return this.manager.setEnabled(id, enabled);
  }

  /**
   * 在目标标签页的主世界执行脚本的指定 action。
   * @param {object} p { id, action, args, tab_id }
   * @returns {Promise<object>} { ok, action, result }
   */
  async run({ id, action, args, tab_id }) {
    if (!id) {
      throw cmdError("SCRIPT_INVALID", "id is required");
    }
    if (!action || !String(action).trim()) {
      throw cmdError("SCRIPT_INVALID", "action is required");
    }

    const script = await this.manager.get(id);
    if (script.enabled === false) {
      throw cmdError("SCRIPT_DISABLED", `script disabled: ${id}`);
    }

    const tab = await this._resolveTab(tab_id);

    let results;
    try {
      results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: "MAIN",
        func: runScriptFn,
        args: [script.source, String(action), args ?? null],
      });
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      if (/Cannot access|chrome:\/\/|extension/i.test(msg)) {
        throw cmdError("PROTECTED_PAGE", msg);
      }
      throw cmdError("EXEC_ERROR", msg);
    }

    const out = results && results.length ? results[0].result : null;
    if (!out || !out.ok) {
      const reason = (out && out.error) || "script run failed";
      throw cmdError("SCRIPT_RUN_ERROR", reason);
    }
    return { ok: true, action: String(action), result: out.value };
  }

  // ---------------- 内部工具 ----------------

  /** 解析目标标签页：未指定则取当前窗口的活动标签页。 */
  async _resolveTab(tabId) {
    if (tabId != null) {
      try {
        return await chrome.tabs.get(tabId);
      } catch (e) {
        throw cmdError("NO_TAB", `tab not found: ${tabId}`);
      }
    }
    const [active] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });
    if (!active) throw cmdError("NO_TAB", "no active tab");
    return active;
  }
}

/**
 * 注入到页面主世界的函数（必须自包含，不能引用外部变量）。
 *
 * 逻辑：求值脚本源码得到脚本对象 → 取 actions[actionName] → 调用其 run(args)。
 *
 * @param {string} source 脚本源码
 * @param {string} actionName 要调用的 action 名
 * @param {object|null} args 传给 action 的参数
 * @returns {Promise<{ok:boolean, value?:any, error?:string}>}
 */
export async function runScriptFn(source, actionName, args) {
  try {
    const src = String(source);

    // 1) 求值脚本源码，得到脚本对象。
    //    兼容两种导出写法：
    //      (a) globalThis.__JARVIS_SCRIPT__ = {...}
    //      (b) module.exports = {...}
    //    注意：new Function 作用域内没有 module，需显式作为形参传入。
    const dummyModule = { exports: {} };
    let scriptObj = null;
    // 先清掉上一次执行可能残留的全局导出，避免读到旧脚本对象。
    try {
      delete globalThis.__JARVIS_SCRIPT__;
    } catch (e) {
      globalThis.__JARVIS_SCRIPT__ = undefined;
    }
    try {
      const factory = new Function("module", "exports", src);
      factory(dummyModule, dummyModule.exports);
    } catch (e) {
      return { ok: false, error: (e && e.message) || String(e) };
    }

    if (dummyModule.exports && Object.keys(dummyModule.exports).length) {
      scriptObj = dummyModule.exports;
    } else if (globalThis.__JARVIS_SCRIPT__) {
      scriptObj = globalThis.__JARVIS_SCRIPT__;
    }

    if (!scriptObj || typeof scriptObj !== "object") {
      return { ok: false, error: "script did not export an object" };
    }

    // 2) 取 action 条目。
    const actions = scriptObj.actions;
    if (!actions || typeof actions !== "object") {
      return { ok: false, error: "script has no 'actions' map" };
    }
    const entry = actions[actionName];
    if (!entry) {
      return { ok: false, error: `action not found: ${actionName}` };
    }

    // 3) 兼容两种写法：entry.run(args) 或 entry 本身即函数。
    const run = typeof entry === "function" ? entry : entry.run;
    if (typeof run !== "function") {
      return {
        ok: false,
        error: `action has no runnable function: ${actionName}`,
      };
    }

    const value = await run(args || {});
    return { ok: true, value: safeSerialize(value) };
  } catch (e) {
    return { ok: false, error: (e && e.message) || String(e) };
  }

  /** 把返回值转成可 JSON 序列化的形式。 */
  function safeSerialize(v) {
    if (v === undefined || v === null) return null;
    const t = typeof v;
    if (t === "string" || t === "number" || t === "boolean") return v;
    try {
      return JSON.parse(JSON.stringify(v));
    } catch (e) {
      return String(v);
    }
  }
}

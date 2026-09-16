// DOM 执行器：通过 content script 在页面内读写 DOM。
//
// 采用 chrome.scripting.executeScript 注入函数，避免依赖常驻 content script。

import { cmdError } from "../command_router.js";

export class DomExecutor {
  /** 查询元素信息。 */
  async query({ tab_id, selector, all }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    const result = await this._exec(tab.id, queryFn, [selector, !!all]);
    return result;
  }

  /** 读取元素文本。 */
  async getText({ tab_id, selector }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    const result = await this._exec(tab.id, getTextFn, [selector]);
    if (result == null) {
      throw cmdError("ELEMENT_NOT_FOUND", `element not found: ${selector}`);
    }
    return { text: result };
  }

  /** 读取元素 HTML。 */
  async getHtml({ tab_id, selector }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    const result = await this._exec(tab.id, getHtmlFn, [selector]);
    if (result == null) {
      throw cmdError("ELEMENT_NOT_FOUND", `element not found: ${selector}`);
    }
    return { html: result };
  }

  /** 点击元素。 */
  async click({ tab_id, selector }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    const ok = await this._exec(tab.id, clickFn, [selector]);
    if (!ok) {
      throw cmdError("ELEMENT_NOT_FOUND", `element not found: ${selector}`);
    }
    return { ok: true };
  }

  /** 输入文本（先聚焦、清空，再设置值并派发事件）。 */
  async type({ tab_id, selector, text, clear }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    const ok = await this._exec(tab.id, typeFn, [
      selector,
      text ?? "",
      clear !== false,
    ]);
    if (!ok) {
      throw cmdError("ELEMENT_NOT_FOUND", `element not found: ${selector}`);
    }
    return { ok: true };
  }

  /** 悬停元素。 */
  async hover({ tab_id, selector }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    const ok = await this._exec(tab.id, hoverFn, [selector]);
    if (!ok) {
      throw cmdError("ELEMENT_NOT_FOUND", `element not found: ${selector}`);
    }
    return { ok: true };
  }

  /** 选择下拉项。 */
  async select({ tab_id, selector, value }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    const ok = await this._exec(tab.id, selectFn, [selector, value]);
    if (!ok) {
      throw cmdError("ELEMENT_NOT_FOUND", `element not found: ${selector}`);
    }
    return { ok: true };
  }

  /** 等待元素出现/消失。 */
  async waitFor({ tab_id, selector, state, timeout_ms }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    const timeout = typeof timeout_ms === "number" ? timeout_ms : 15000;
    const targetState = state || "visible";
    const ok = await this._exec(tab.id, waitForFn, [
      selector,
      targetState,
      timeout,
    ]);
    if (!ok) {
      throw cmdError(
        "TIMEOUT",
        `wait_for timeout: ${selector} (${targetState})`,
      );
    }
    return { ok: true };
  }

  /** 按下键盘按键（可选先聚焦指定元素，否则作用于当前焦点元素）。 */
  async pressKey({ tab_id, selector, key }) {
    const tab = await this._resolveTab(tab_id);
    if (!key || !String(key).trim()) {
      throw cmdError("EXEC_ERROR", "key is required");
    }
    const result = await this._exec(tab.id, pressKeyFn, [
      selector || "",
      String(key),
    ]);
    if (!result || !result.ok) {
      const reason = (result && result.error) || "press_key failed";
      throw cmdError(
        reason === "element not found" ? "ELEMENT_NOT_FOUND" : "EXEC_ERROR",
        reason,
      );
    }
    return { ok: true, key: result.key, target: result.target };
  }

  /** 滚动页面：指定 selector 则滚动到该元素，否则按 x/y 像素滚动。 */
  async scroll({ tab_id, selector, x, y, behavior }) {
    const tab = await this._resolveTab(tab_id);
    const result = await this._exec(tab.id, scrollFn, [
      selector || "",
      typeof x === "number" ? x : 0,
      typeof y === "number" ? y : 0,
      behavior === "smooth" ? "smooth" : "auto",
    ]);
    if (!result || !result.ok) {
      const reason = (result && result.error) || "scroll failed";
      throw cmdError(
        reason === "element not found" ? "ELEMENT_NOT_FOUND" : "EXEC_ERROR",
        reason,
      );
    }
    return result;
  }

  /** 在页面中执行任意 JS 代码（兜底能力，高危）。 */
  async execute({ tab_id, code, world }) {
    const tab = await this._resolveTab(tab_id);
    if (!code || !String(code).trim()) {
      throw cmdError("EXEC_ERROR", "code is required");
    }
    // 默认在 MAIN 世界执行：ISOLATED 世界里的 new Function 会被页面 CSP
    // 的 unsafe-eval 拦截（多数站点均有该限制），导致执行必然失败。
    // 显式传 world: "ISOLATED" 时仍按用户要求执行。
    const targetWorld = world === "ISOLATED" ? "ISOLATED" : "MAIN";
    const result = await this._execInWorld(
      tab.id,
      executeFn,
      [String(code)],
      targetWorld,
    );
    if (!result || !result.ok) {
      const reason = (result && result.error) || "script execution failed";
      throw cmdError("EXEC_ERROR", reason);
    }
    return { ok: true, result: result.value };
  }

  /**
   * 上传本地文件到 file input。
   * 通过 chrome.debugger 的 DOM.setFileInputFiles 设置真实文件路径，
   * 这是扩展中唯一能真实上传本地文件的方式（沙箱内无法读取本地文件内容）。
   */
  async uploadFile({ tab_id, selector, file_path }) {
    const tab = await this._resolveTab(tab_id);
    this._requireSelector(selector);
    if (!file_path || !String(file_path).trim()) {
      throw cmdError("EXEC_ERROR", "file_path is required");
    }
    if (!chrome.debugger) {
      throw cmdError(
        "EXEC_ERROR",
        'chrome.debugger API unavailable (requires "debugger" permission)',
      );
    }

    // 1. 找到 file input 的 backendNodeId
    const target = { tabId: tab.id };
    let attached = false;
    try {
      await chrome.debugger.attach(target, "1.3");
      attached = true;
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      // 已被其他调试器占用时无法附加
      throw cmdError("EXEC_ERROR", `failed to attach debugger: ${msg}`);
    }

    try {
      await chrome.debugger.sendCommand(target, "DOM.enable");
      const doc = await chrome.debugger.sendCommand(target, "DOM.getDocument", {
        depth: -1,
        pierce: true,
      });
      const node = await chrome.debugger.sendCommand(
        target,
        "DOM.querySelector",
        {
          nodeId: doc.root.nodeId,
          selector: String(selector),
        },
      );
      if (!node || !node.nodeId) {
        throw cmdError("ELEMENT_NOT_FOUND", `element not found: ${selector}`);
      }
      await chrome.debugger.sendCommand(target, "DOM.setFileInputFiles", {
        files: [String(file_path)],
        nodeId: node.nodeId,
      });
      return { ok: true, selector, file_path };
    } finally {
      if (attached) {
        try {
          await chrome.debugger.detach(target);
        } catch (e) {
          // 忽略 detach 失败
        }
      }
    }
  }

  // ---------------- 内部工具 ----------------

  _requireSelector(selector) {
    if (!selector || !String(selector).trim()) {
      throw cmdError("EXEC_ERROR", "selector is required");
    }
  }

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

  async _exec(tabId, func, args) {
    return this._execInWorld(tabId, func, args, "ISOLATED");
  }

  async _execInWorld(tabId, func, args, world) {
    let results;
    try {
      results = await chrome.scripting.executeScript({
        target: { tabId },
        world,
        func,
        args,
      });
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      if (/Cannot access|chrome:\/\/|extension/i.test(msg)) {
        throw cmdError("PROTECTED_PAGE", msg);
      }
      throw cmdError("EXEC_ERROR", msg);
    }
    if (!results || !results.length) return null;
    return results[0].result;
  }
}

// ---------------- 注入到页面的函数（必须自包含，不能引用外部变量） ----------------

function queryFn(selector, all) {
  const toInfo = (el) => ({
    tag: el.tagName ? el.tagName.toLowerCase() : null,
    text: (el.innerText || el.textContent || "").trim().slice(0, 500),
    value: el.value ?? null,
    id: el.id || null,
    class: el.className || null,
  });
  if (all) {
    const nodes = Array.from(document.querySelectorAll(selector));
    return { count: nodes.length, items: nodes.map(toInfo) };
  }
  const el = document.querySelector(selector);
  return el ? toInfo(el) : null;
}

function getTextFn(selector) {
  const el = document.querySelector(selector);
  if (!el) return null;
  return (el.innerText || el.textContent || "").trim();
}

function getHtmlFn(selector) {
  const el = document.querySelector(selector);
  if (!el) return null;
  return el.innerHTML;
}

function clickFn(selector) {
  const el = document.querySelector(selector);
  if (!el) return false;
  el.scrollIntoView({ block: "center" });
  el.click();
  return true;
}

function typeFn(selector, text, clear) {
  const el = document.querySelector(selector);
  if (!el) return false;
  el.focus();
  if (clear) {
    el.value = "";
  }
  // 兼容 React/Vue 等受控组件：使用原生 setter 再派发 input 事件
  const proto =
    el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) {
    setter.call(el, clear ? text : (el.value || "") + text);
  } else {
    el.value = clear ? text : (el.value || "") + text;
  }
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

function hoverFn(selector) {
  const el = document.querySelector(selector);
  if (!el) return false;
  el.scrollIntoView({ block: "center" });
  const rect = el.getBoundingClientRect();
  const opts = {
    bubbles: true,
    cancelable: true,
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
  };
  el.dispatchEvent(new MouseEvent("mouseover", opts));
  el.dispatchEvent(new MouseEvent("mouseenter", opts));
  el.dispatchEvent(new MouseEvent("mousemove", opts));
  return true;
}

function selectFn(selector, value) {
  const el = document.querySelector(selector);
  if (!el) return false;
  el.value = value;
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

async function waitForFn(selector, state, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  const check = () => {
    const el = document.querySelector(selector);
    if (state === "hidden") return !el || !isVisible(el);
    if (state === "attached") return !!el;
    return !!el && isVisible(el);
  };
  const isVisible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.visibility !== "hidden" &&
      style.display !== "none"
    );
  };
  while (Date.now() < deadline) {
    if (check()) return true;
    await new Promise((r) => setTimeout(r, 200));
  }
  return false;
}

function pressKeyFn(selector, key) {
  let el = null;
  if (selector) {
    el = document.querySelector(selector);
    if (!el) return { ok: false, error: "element not found" };
    el.focus();
  } else {
    el = document.activeElement || document.body;
  }

  const target = el || document.body;
  const opts = {
    key,
    code: key,
    bubbles: true,
    cancelable: true,
  };
  // 常见按键的 keyCode/which，兼容依赖旧属性的页面
  const legacy = {
    Enter: 13,
    Escape: 27,
    Tab: 9,
    Backspace: 8,
    Delete: 46,
    ArrowUp: 38,
    ArrowDown: 40,
    ArrowLeft: 37,
    ArrowRight: 39,
    " ": 32,
  };
  if (legacy[key] != null) {
    opts.keyCode = legacy[key];
    opts.which = legacy[key];
  }

  const down = new KeyboardEvent("keydown", opts);
  const press = new KeyboardEvent("keypress", opts);
  const up = new KeyboardEvent("keyup", opts);
  target.dispatchEvent(down);
  target.dispatchEvent(press);
  target.dispatchEvent(up);

  // Enter 在表单输入框内时尝试提交表单（浏览器默认行为不会因合成事件触发）
  if (
    key === "Enter" &&
    el &&
    el.form &&
    typeof el.form.requestSubmit === "function"
  ) {
    try {
      el.form.requestSubmit();
    } catch (e) {
      // 忽略：部分表单不支持 requestSubmit
    }
  }

  return {
    ok: true,
    key,
    target: target.tagName ? target.tagName.toLowerCase() : null,
  };
}

function scrollFn(selector, x, y, behavior) {
  if (selector) {
    const el = document.querySelector(selector);
    if (!el) return { ok: false, error: "element not found" };
    el.scrollIntoView({ behavior, block: "center" });
  } else {
    window.scrollBy({ left: x, top: y, behavior });
  }
  return {
    ok: true,
    scroll_x: window.scrollX,
    scroll_y: window.scrollY,
    page_height: document.documentElement.scrollHeight,
    viewport_height: window.innerHeight,
  };
}

function executeFn(code) {
  try {
    // 说明：new Function 在页面上下文受页面 CSP 的 unsafe-eval 限制，
    // 因此 script.execute 默认以 MAIN 世界执行（见 execute()）。
    // 支持三种写法：表达式（如 "1+1"）、语句块（如 "const x=1; return x;"）、
    // 以及带 return 的语句块——统一用 async 函数包裹，允许 await。
    const src = String(code);
    const fn = new Function(
      '"use strict";return (async () => {' + src + "\n})();",
    );
    let value;
    try {
      value = fn();
    } catch (e) {
      // 语句块解析失败时，退化为按表达式求值
      const exprFn = new Function('"use strict";return (' + src + ");");
      value = exprFn();
    }
    return Promise.resolve(value)
      .then((v) => ({ ok: true, value: safeSerialize(v) }))
      .catch((e) => ({ ok: false, error: (e && e.message) || String(e) }));
  } catch (e) {
    return { ok: false, error: (e && e.message) || String(e) };
  }

  function safeSerialize(v) {
    if (v === undefined) return null;
    if (v === null) return null;
    const t = typeof v;
    if (t === "string" || t === "number" || t === "boolean") return v;
    try {
      return JSON.parse(JSON.stringify(v));
    } catch (e) {
      return String(v);
    }
  }
}

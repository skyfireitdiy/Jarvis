// 调试执行器：读取页面 console 输出（相当于 F12 Console 面板），
// 并通过 chrome.debugger（CDP）提供不受 CSP 限制的脚本求值与网络请求采集。
//
// 关键点：console 是页面主世界的对象，必须注入到 MAIN 世界才能 hook 到
// 页面自身的 console 调用（ISOLATED 世界看到的是另一份 console 对象）。
// hook 采用幂等设计，可重复注入而不重复包裹。
//
// CDP 相关能力（debugger.evaluate / network.get_requests）走 chrome.debugger，
// 不依赖页面 CSP，可执行任意表达式（含 unsafe-eval 被禁的站点）。

import { cmdError } from "../command_router.js";

// 网络请求采集的全局状态：tabId -> { records, attachedByUs, timer }
const networkState = new Map();

export class DebugExecutor {
  /**
   * 读取页面 console 日志。
   * @param {object} p
   * @param {number} [p.tab_id] 目标标签页，缺省为当前活动标签页
   * @param {number} [p.limit] 返回最近多少条，默认 100
   * @param {boolean} [p.clear] 读取后是否清空缓存
   */
  async getLogs({ tab_id, limit, clear }) {
    const tab = await this._resolveTab(tab_id);
    const max =
      typeof limit === "number" && limit > 0 ? Math.floor(limit) : 100;

    // 1. 确保 hook 已安装（幂等，重复注入无副作用）
    await this._execInWorld(tab.id, consoleHookFn, [], "MAIN");

    // 2. 读取缓存快照
    const result = await this._execInWorld(
      tab.id,
      readLogsFn,
      [max, !!clear],
      "MAIN",
    );
    if (!result || !result.ok) {
      const reason = (result && result.error) || "failed to read console logs";
      throw cmdError("EXEC_ERROR", reason);
    }
    return { logs: result.logs, count: result.count };
  }

  /**
   * 通过 CDP 在页面中求值任意表达式（不受页面 CSP 的 unsafe-eval 限制）。
   * 相当于 F12 Console 里直接敲表达式。
   * @param {object} p
   * @param {number} [p.tab_id] 目标标签页
   * @param {string} p.expression 要执行的表达式/语句
   * @param {boolean} [p.await_promise] 是否等待 Promise 结果，默认 true
   */
  async evaluate({ tab_id, expression, await_promise }) {
    const tab = await this._resolveTab(tab_id);
    if (!expression || !String(expression).trim()) {
      throw cmdError("EXEC_ERROR", "expression is required");
    }
    const target = { tabId: tab.id };
    const attachedByUs = await this._attach(target);
    try {
      await chrome.debugger.sendCommand(target, "Runtime.enable");
      const res = await chrome.debugger.sendCommand(
        target,
        "Runtime.evaluate",
        {
          expression: String(expression),
          returnByValue: true,
          awaitPromise: await_promise !== false,
          allowUnsafeEvalBlockedByCSP: true,
          userGesture: true,
        },
      );
      if (res && res.exceptionDetails) {
        const d = res.exceptionDetails;
        const msg =
          (d.exception && (d.exception.description || d.exception.value)) ||
          d.text ||
          "evaluation failed";
        throw cmdError("EXEC_ERROR", String(msg));
      }
      return {
        ok: true,
        result: res && res.result ? res.result.value : null,
        type: res && res.result ? res.result.type : null,
      };
    } finally {
      if (attachedByUs) await this._detach(target);
    }
  }

  /**
   * 透传任意 CDP 命令（相当于直接使用 DevTools Protocol）。
   * 用于 Runtime/DOM 域之外的场景，如 Page.addScriptToEvaluateOnNewDocument
   * （在文档创建前注入脚本，可 hook 页面自身的绘制/网络行为）。
   * @param {object} p
   * @param {number} [p.tab_id] 目标标签页
   * @param {string} p.method CDP 方法名，如 "Page.addScriptToEvaluateOnNewDocument"
   * @param {object} [p.params] CDP 方法参数
   */
  async sendCommand({ tab_id, method, params }) {
    const tab = await this._resolveTab(tab_id);
    const cmd = String(method || "").trim();
    if (!cmd) {
      throw cmdError("EXEC_ERROR", "method is required");
    }
    const target = { tabId: tab.id };
    const attachedByUs = await this._attach(target);
    try {
      const res = await chrome.debugger.sendCommand(
        target,
        cmd,
        params && typeof params === "object" ? params : {},
      );
      return { ok: true, result: res === undefined ? null : res };
    } finally {
      if (attachedByUs) await this._detach(target);
    }
  }

  /**
   * 采集页面网络请求（相当于 F12 Network 面板）。
   * 通过 CDP Network 域监听，采集 duration_ms 毫秒后返回。
   * @param {object} p
   * @param {number} [p.tab_id] 目标标签页
   * @param {number} [p.duration_ms] 采集时长，默认 3000
   * @param {number} [p.limit] 最多返回多少条，默认 100
   * @param {string} [p.filter] 按 URL 子串过滤
   */
  async getRequests({ tab_id, duration_ms, limit, filter }) {
    const tab = await this._resolveTab(tab_id);
    const duration =
      typeof duration_ms === "number" && duration_ms > 0 ? duration_ms : 3000;
    const max =
      typeof limit === "number" && limit > 0 ? Math.floor(limit) : 100;

    const target = { tabId: tab.id };
    const attachedByUs = await this._attach(target);
    const records = [];
    const byRequestId = new Map();

    const onEvent = (source, method, params) => {
      if (!source || source.tabId !== tab.id) return;
      if (method === "Network.requestWillBeSent") {
        const rec = {
          request_id: params.requestId,
          url: params.request.url,
          method: params.request.method,
          type: params.type || null,
          status: null,
          status_text: null,
          mime_type: null,
          encoded_data_length: null,
          started_at: Date.now(),
          duration_ms: null,
          failed: null,
        };
        byRequestId.set(params.requestId, rec);
        records.push(rec);
      } else if (method === "Network.responseReceived") {
        const rec = byRequestId.get(params.requestId);
        if (rec) {
          rec.status = params.response.status;
          rec.status_text = params.response.statusText;
          rec.mime_type = params.response.mimeType;
          rec.type = params.type || rec.type;
        }
      } else if (method === "Network.loadingFinished") {
        const rec = byRequestId.get(params.requestId);
        if (rec) {
          rec.encoded_data_length = params.encodedDataLength;
          rec.duration_ms = Date.now() - rec.started_at;
        }
      } else if (method === "Network.loadingFailed") {
        const rec = byRequestId.get(params.requestId);
        if (rec) {
          rec.failed = params.errorText || "failed";
          rec.duration_ms = Date.now() - rec.started_at;
        }
      }
    };

    chrome.debugger.onEvent.addListener(onEvent);
    try {
      await chrome.debugger.sendCommand(target, "Network.enable");
      await sleep(duration);
      try {
        await chrome.debugger.sendCommand(target, "Network.disable");
      } catch (e) {
        // 忽略：目标可能已关闭
      }
    } finally {
      chrome.debugger.onEvent.removeListener(onEvent);
      if (attachedByUs) await this._detach(target);
    }

    let out = records;
    if (filter) {
      const needle = String(filter);
      out = out.filter((r) => r.url && r.url.includes(needle));
    }
    const total = out.length;
    if (out.length > max) out = out.slice(-max);
    return { requests: out, count: total, duration_ms: duration };
  }

  // ---------------- 内部工具 ----------------

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

  /** 附加调试器；返回是否由本次调用附加（用于决定是否 detach）。 */
  async _attach(target) {
    if (!chrome.debugger) {
      throw cmdError(
        "EXEC_ERROR",
        'chrome.debugger API unavailable (requires "debugger" permission)',
      );
    }
    try {
      const targets = await chrome.debugger.getTargets();
      const existing = targets.find(
        (t) => t.tabId === target.tabId && t.attached,
      );
      if (existing) return false;
    } catch (e) {
      // getTargets 不可用时按未附加处理
    }
    try {
      await chrome.debugger.attach(target, "1.3");
      return true;
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      throw cmdError("EXEC_ERROR", `failed to attach debugger: ${msg}`);
    }
  }

  /** 分离调试器（忽略失败）。 */
  async _detach(target) {
    try {
      await chrome.debugger.detach(target);
    } catch (e) {
      // 忽略 detach 失败
    }
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
/** 安装 console hook（幂等）。注入到 MAIN 世界。 */
function consoleHookFn() {
  if (window.__jarvisConsoleHooked) return { ok: true, hooked: false };

  const MAX_LOGS = 500;
  const logs = [];
  window.__jarvisConsoleLogs = logs;

  /** 安全序列化单个参数，避免循环引用/Error/DOM 节点导致失败。 */
  function serializeArg(v) {
    try {
      if (v === undefined) return "undefined";
      if (v === null) return "null";
      const t = typeof v;
      if (t === "string") return v;
      if (t === "number" || t === "boolean" || t === "bigint") return String(v);
      if (t === "function") {
        return `[Function ${v.name || "anonymous"}]`;
      }
      if (t === "symbol") return String(v);
      // Error 对象：保留 message 与 stack
      if (v instanceof Error) {
        return v.stack
          ? `${v.name}: ${v.message}\n${v.stack}`
          : `${v.name}: ${v.message}`;
      }
      // DOM 节点：转成简短描述
      if (typeof Node !== "undefined" && v instanceof Node) {
        const tag = v.tagName ? v.tagName.toLowerCase() : v.nodeName;
        const id = v.id ? `#${v.id}` : "";
        const cls =
          v.className && typeof v.className === "string"
            ? `.${v.className.trim().split(/\s+/).join(".")}`
            : "";
        return `<${tag}${id}${cls}>`;
      }
      // 普通对象：尝试 JSON 序列化，失败则降级为 String()
      const seen = new WeakSet();
      return JSON.stringify(v, (key, val) => {
        if (typeof val === "object" && val !== null) {
          if (seen.has(val)) return "[Circular]";
          seen.add(val);
        }
        if (typeof val === "function")
          return `[Function ${val.name || "anonymous"}]`;
        if (typeof val === "bigint") return String(val);
        return val;
      });
    } catch (e) {
      try {
        return String(v);
      } catch (e2) {
        return "[Unserializable]";
      }
    }
  }

  /** 追加一条日志（环形缓冲，超出上限丢弃最旧）。 */
  function push(level, args) {
    try {
      logs.push({
        level,
        timestamp: Date.now(),
        args: Array.prototype.map.call(args, serializeArg),
      });
      while (logs.length > MAX_LOGS) logs.shift();
    } catch (e) {
      // 记录日志本身失败时静默忽略，避免影响页面
    }
  }

  // 1. hook console 各方法
  const levels = ["log", "info", "warn", "error", "debug"];
  for (const level of levels) {
    const original = console[level];
    console[level] = function (...args) {
      push(level, args);
      if (typeof original === "function") {
        try {
          original.apply(console, args);
        } catch (e) {
          // 忽略原方法异常
        }
      }
    };
  }

  // 2. hook 未捕获异常
  const originalOnError = window.onerror;
  window.onerror = function (message, source, lineno, colno, error) {
    const detail =
      error instanceof Error
        ? `${error.name}: ${error.message}`
        : String(message);
    push("error", [
      `${detail} (${source || "?"}:${lineno || 0}:${colno || 0})`,
    ]);
    if (typeof originalOnError === "function") {
      try {
        return originalOnError.apply(window, arguments);
      } catch (e) {
        // 忽略
      }
    }
    return false;
  };

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event && event.reason;
    const detail =
      reason instanceof Error
        ? `${reason.name}: ${reason.message}`
        : serializeArg(reason);
    push("error", [`UnhandledPromiseRejection: ${detail}`]);
  });

  window.__jarvisConsoleHooked = true;
  return { ok: true, hooked: true };
}

/** 读取日志缓存快照，可选清空。注入到 MAIN 世界。 */
function readLogsFn(limit, clear) {
  try {
    const logs = window.__jarvisConsoleLogs;
    if (!Array.isArray(logs)) {
      return { ok: true, logs: [], count: 0 };
    }
    const count = logs.length;
    const slice = limit > 0 ? logs.slice(-limit) : logs.slice();
    if (clear) {
      logs.length = 0;
    }
    return { ok: true, logs: slice, count };
  } catch (e) {
    return { ok: false, error: (e && e.message) || String(e) };
  }
}

/** 简单延时。 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

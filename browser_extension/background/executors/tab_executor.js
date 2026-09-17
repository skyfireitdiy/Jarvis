// 标签页与导航执行器：封装 chrome.tabs 相关操作。

import { cmdError } from "../command_router.js";

export class TabExecutor {
  /** 列出所有标签页。 */
  async list() {
    const tabs = await chrome.tabs.query({});
    return tabs.map((t) => ({
      tab_id: t.id,
      url: t.url,
      title: t.title,
      active: t.active,
      window_id: t.windowId,
    }));
  }

  /** 激活指定标签页。 */
  async activate({ tab_id }) {
    if (tab_id == null) throw cmdError("NO_TAB", "tab_id is required");
    const tab = await this._getTab(tab_id);
    await chrome.tabs.update(tab.id, { active: true });
    if (tab.windowId != null) {
      try {
        await chrome.windows.update(tab.windowId, { focused: true });
      } catch (e) {
        // 某些环境下不允许聚焦窗口，忽略
      }
    }
    return { ok: true, tab_id: tab.id };
  }

  /** 关闭指定标签页。 */
  async close({ tab_id }) {
    if (tab_id == null) throw cmdError("NO_TAB", "tab_id is required");
    await this._getTab(tab_id);
    await chrome.tabs.remove(tab_id);
    return { ok: true, tab_id };
  }

  /**
   * 新建标签页。
   * new_window 为 true（默认）时优先在「不含 Jarvis 前端页面」的窗口中新建标签页，
   * 避免把自动化打开的页面混进用户查看 Jarvis 的那个窗口；
   * 仅当所有窗口都含 Jarvis 前端页面（无处可放）时才新开窗口。
   * new_window 为 false 时退回在当前窗口新建标签页。
   */
  async create({ url, active, new_window }) {
    const target = url || "about:blank";
    if (new_window !== false) {
      const windowId = await this._pickTargetWindowId();
      if (windowId != null) {
        const tab = await chrome.tabs.create({
          url: target,
          active: active !== false,
          windowId,
        });
        return {
          ok: true,
          tab_id: tab.id,
          window_id: tab.windowId,
          url: tab.url,
          new_window: false,
        };
      }
      const win = await chrome.windows.create({
        url: target,
        focused: active !== false,
      });
      const tab = win && win.tabs && win.tabs.length ? win.tabs[0] : null;
      return {
        ok: true,
        tab_id: tab ? tab.id : null,
        window_id: win ? win.id : null,
        url: tab ? tab.url : target,
        new_window: true,
      };
    }
    const tab = await chrome.tabs.create({
      url: target,
      active: active !== false,
    });
    return {
      ok: true,
      tab_id: tab.id,
      window_id: tab.windowId,
      url: tab.url,
      new_window: false,
    };
  }

  /** 导航到指定 URL。 */
  async navigate({ tab_id, url, wait_until, new_window }) {
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    let tabId = tab_id;
    if (tabId == null) {
      // 未指定 tab_id 时复用 create 的逻辑（优先在非 Jarvis 窗口新建标签页）
      const created = await this.create({ url, new_window });
      tabId = created.tab_id;
      if (tabId != null && wait_until !== "none") {
        await this._waitForComplete(tabId);
      }
      return { ok: true, tab_id: tabId, url, new_window: created.new_window };
    }
    await this._getTab(tabId);
    await chrome.tabs.update(tabId, { url });
    if (wait_until !== "none") {
      await this._waitForComplete(tabId);
    }
    const tab = await chrome.tabs.get(tabId);
    return { ok: true, tab_id: tabId, url: tab.url, title: tab.title };
  }

  /** 重新加载标签页。 */
  async reload({ tab_id }) {
    const tab = await this._resolveTab(tab_id);
    await chrome.tabs.reload(tab.id);
    await this._waitForComplete(tab.id);
    return { ok: true, tab_id: tab.id };
  }

  /** 后退。 */
  async back({ tab_id }) {
    const tab = await this._resolveTab(tab_id);
    await chrome.tabs.goBack(tab.id);
    return { ok: true, tab_id: tab.id };
  }

  /** 前进。 */
  async forward({ tab_id }) {
    const tab = await this._resolveTab(tab_id);
    await chrome.tabs.goForward(tab.id);
    return { ok: true, tab_id: tab.id };
  }

  /**
   * 读取页面基础信息（URL、标题、就绪状态、视口/滚动/文档尺寸）。
   */
  async getInfo({ tab_id }) {
    const tab = await this._resolveTab(tab_id);
    let info = null;
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: "ISOLATED",
        func: pageInfoFn,
      });
      info = results && results.length ? results[0].result : null;
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      if (/Cannot access|chrome:\/\/|extension/i.test(msg)) {
        throw cmdError("PROTECTED_PAGE", msg);
      }
      throw cmdError("EXEC_ERROR", msg);
    }
    if (!info) {
      throw cmdError("EXEC_ERROR", "failed to read page info");
    }
    return {
      tab_id: tab.id,
      url: info.url,
      title: info.title,
      ready_state: info.ready_state,
      viewport: info.viewport,
      scroll: info.scroll,
      document: info.document,
    };
  }

  // ---------------- 内部工具 ----------------

  /**
   * 挑选「新建标签页」应放入的窗口，返回 window_id；返回 null 表示无处可放（需新开窗口）。
   *
   * 规则：排除所有含 Jarvis 前端页面的窗口（这些窗口留给用户查看 Jarvis，不掺入自动化页面），
   * 在剩余窗口里优先选最后聚焦的那个；若所有窗口都含 Jarvis 前端页面，则返回 null。
   */
  async _pickTargetWindowId() {
    const windows = await chrome.windows.getAll({ populate: true });
    if (!windows.length) return null;
    // 并行探测各窗口是否含 Jarvis 前端页面（串行会随标签页数量线性变慢）
    const jarvisFlags = await Promise.all(
      windows.map((win) => this._windowHasJarvisPage(win)),
    );
    const candidates = windows.filter((_, i) => !jarvisFlags[i]);
    if (!candidates.length) return null;
    // 优先用最后聚焦的候选窗口，符合用户直觉
    try {
      const lastFocused = await chrome.windows.getLastFocused();
      if (lastFocused && candidates.some((w) => w.id === lastFocused.id)) {
        return lastFocused.id;
      }
    } catch (e) {
      // 某些环境下无法获取最后聚焦窗口，退回到第一个候选窗口
    }
    return candidates[0].id;
  }

  /** 判定某窗口内是否存在 Jarvis 前端页面（窗口内任一标签页命中即可）。 */
  async _windowHasJarvisPage(win) {
    const tabs = (win && win.tabs) || [];
    const flags = await Promise.all(tabs.map((tab) => this._isJarvisPage(tab)));
    return flags.some(Boolean);
  }

  /**
   * 判定标签页是否为 Jarvis 前端页面。
   * 依据页面主世界暴露的 window.__jarvisAuthBridge（与 service_worker 探测登录态的方式一致），
   * 而非 URL 特征——Jarvis 前端与网关可能不同域名，URL 无法可靠识别。
   */
  async _isJarvisPage(tab) {
    if (!tab || tab.id == null) return false;
    if (!/^https?:/i.test(tab.url || "")) return false;
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: hasJarvisAuthBridgeFn,
        world: "MAIN",
      });
      return Boolean(results && results[0] && results[0].result);
    } catch (e) {
      // 受限页面（chrome://、扩展页等）无法注入，视为非 Jarvis 页面
      return false;
    }
  }

  async _getTab(tabId) {
    try {
      return await chrome.tabs.get(tabId);
    } catch (e) {
      throw cmdError("NO_TAB", `tab not found: ${tabId}`);
    }
  }

  /** 未指定 tab_id 时使用当前活动标签页。 */
  async _resolveTab(tabId) {
    if (tabId != null) return this._getTab(tabId);
    const [active] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });
    if (!active) throw cmdError("NO_TAB", "no active tab");
    return active;
  }

  /** 等待标签页加载完成（简单轮询 status）。 */
  async _waitForComplete(tabId, timeoutMs = 15000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const tab = await chrome.tabs.get(tabId);
        if (tab.status === "complete") return;
      } catch (e) {
        throw cmdError("NO_TAB", `tab not found: ${tabId}`);
      }
      await sleep(150);
    }
    // 超时不视为致命错误，交由后续操作决定
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// 注入到页面的函数（必须自包含，不能引用外部变量）
function hasJarvisAuthBridgeFn() {
  try {
    return Boolean(window.__jarvisAuthBridge);
  } catch (e) {
    return false;
  }
}

// 注入到页面的函数（必须自包含，不能引用外部变量）
function pageInfoFn() {
  const doc = document.documentElement;
  return {
    url: location.href,
    title: document.title,
    ready_state: document.readyState,
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
    },
    scroll: {
      x: window.scrollX,
      y: window.scrollY,
    },
    document: {
      width: doc ? doc.scrollWidth : 0,
      height: doc ? doc.scrollHeight : 0,
    },
  };
}

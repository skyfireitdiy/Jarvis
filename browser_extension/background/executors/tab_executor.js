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

  /** 新建标签页。 */
  async create({ url, active }) {
    const tab = await chrome.tabs.create({
      url: url || "about:blank",
      active: active !== false,
    });
    return { ok: true, tab_id: tab.id, url: tab.url };
  }

  /** 导航到指定 URL。 */
  async navigate({ tab_id, url, wait_until }) {
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    let tabId = tab_id;
    if (tabId == null) {
      // 未指定 tab_id 时新建标签页
      const tab = await chrome.tabs.create({ url, active: true });
      return { ok: true, tab_id: tab.id, url };
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

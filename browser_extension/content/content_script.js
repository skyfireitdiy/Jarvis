// 页面内 content script。
//
// 职责：响应 background 的页面元信息请求（jarvis_page_info）。
//
// 说明：
// - DOM 操作由 background 通过 chrome.scripting.executeScript 注入函数完成。
// - 登录态 Token 由 background 通过 chrome.scripting.executeScript({ world: "MAIN" })
//   直接在主世界读取 window.__jarvisAuthBridge。
//   不可在内容脚本里动态插入 inline script 来桥接主世界：MV3 下该方式会被页面
//   CSP（script-src 不含 unsafe-inline）拦截，脚本不会执行。
(function () {
  if (window.__jarvisContentScriptLoaded) return;
  window.__jarvisContentScriptLoaded = true;

  // 在 DOM 上留标记：隔离世界与页面主世界共享 DOM，
  // 主世界可通过 document.documentElement.dataset.jarvisCsLoaded 诊断注入状态。
  try {
    document.documentElement.dataset.jarvisCsLoaded = String(Date.now());
  } catch (e) {
    // DOM 尚不可用时忽略
  }

  // 上报 content script 已注入，便于 background 侧诊断
  try {
    chrome.runtime.sendMessage({
      type: "jarvis_cs_loaded",
      url: location.href,
    });
  } catch (e) {
    // 扩展上下文失效时忽略
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !message.type) {
      return false;
    }

    // 页面元信息请求
    if (message.type === "jarvis_page_info") {
      try {
        sendResponse({
          success: true,
          data: {
            url: location.href,
            title: document.title,
            ready_state: document.readyState,
          },
        });
      } catch (e) {
        sendResponse({ success: false, error: String(e) });
      }
      return true;
    }

    return false;
  });
})();

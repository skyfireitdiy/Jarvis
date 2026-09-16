// 页面内 content script。
//
// 职责：
// 1. 作为常驻补充，响应 background 的页面元信息请求（jarvis_page_info）。
// 2. 桥接 Jarvis 网页登录态：向页面主世界注入脚本，读取 window.__jarvisAuthBridge
//    暴露的 Token，并转发给 background，供扩展自动连接网关（无需用户手填 Token）。
//
// 说明：DOM 操作主要由 background 通过 chrome.scripting.executeScript 注入函数完成。

(function () {
  if (window.__jarvisContentScriptLoaded) return;
  window.__jarvisContentScriptLoaded = true;

  // ---------------- 主世界桥接脚本注入 ----------------
  // content script 运行在隔离世界，无法访问页面 JS 变量，
  // 因此注入一段主世界脚本，由它调用页面暴露的 __jarvisAuthBridge。
  function injectMainWorldBridge() {
    const script = document.createElement("script");
    script.textContent = `(${mainWorldBridge.toString()})();`;
    (document.head || document.documentElement).appendChild(script);
    script.remove();
  }

  // 该函数会被序列化后在页面主世界执行。
  function mainWorldBridge() {
    if (window.__jarvisBridgeInjected) return;
    window.__jarvisBridgeInjected = true;

    function readToken() {
      try {
        const bridge = window.__jarvisAuthBridge;
        if (bridge && typeof bridge.getToken === "function") {
          return bridge.getToken() || null;
        }
      } catch (e) {
        // 忽略读取异常
      }
      return null;
    }

    // 响应隔离世界的按需查询
    window.addEventListener("message", (event) => {
      if (event.source !== window) return;
      const data = event.data;
      if (!data || data.type !== "jarvis_ext_get_token") return;
      window.postMessage(
        {
          type: "jarvis_ext_token",
          token: readToken(),
          gateway: location.origin,
        },
        "*",
      );
    });

    // 转发页面广播的 Token 变化
    window.addEventListener("message", (event) => {
      if (event.source !== window) return;
      const data = event.data;
      if (!data || data.type !== "jarvis_token_changed") return;
      window.postMessage(
        {
          type: "jarvis_ext_token_changed",
          token: data.token || null,
          gateway: location.origin,
        },
        "*",
      );
    });
  }

  injectMainWorldBridge();

  // ---------------- 隔离世界：转发给 background ----------------
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data;
    if (!data) return;
    if (
      data.type !== "jarvis_ext_token" &&
      data.type !== "jarvis_ext_token_changed"
    ) {
      return;
    }
    try {
      chrome.runtime.sendMessage({
        type: data.type,
        token: data.token || null,
        gateway: data.gateway || location.origin,
      });
    } catch (e) {
      // 扩展上下文失效（如重载）时会抛错，忽略
    }
  });

  // ---------------- 与 background 的消息处理 ----------------
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

    // background 主动索取登录态 Token（扩展冷启动时）
    if (message.type === "jarvis_request_token") {
      requestTokenFromMainWorld()
        .then((token) =>
          sendResponse({
            success: true,
            token: token || null,
            gateway: location.origin,
          }),
        )
        .catch((e) =>
          sendResponse({
            success: false,
            token: null,
            gateway: location.origin,
            error: String(e),
          }),
        );
      return true; // 异步响应
    }

    return false;
  });

  /**
   * 通过主世界桥接按需读取 Token。
   * 主世界脚本收到 jarvis_ext_get_token 后会回传 jarvis_ext_token。
   */
  function requestTokenFromMainWorld() {
    return new Promise((resolve) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        window.removeEventListener("message", onMessage);
        resolve(null);
      }, 1000);

      function onMessage(event) {
        if (event.source !== window) return;
        const data = event.data;
        if (!data || data.type !== "jarvis_ext_token") return;
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        window.removeEventListener("message", onMessage);
        resolve(data.token || null);
      }

      window.addEventListener("message", onMessage);
      window.postMessage({ type: "jarvis_ext_get_token" }, "*");
    });
  }
})();

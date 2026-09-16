// 剪贴板执行器：把「网关静态文件」或「直接给定的内容」写入前端页面的系统剪贴板。
//
// 为什么读写要分两处：
// - 读文件：在 background（service worker）里 fetch，可跨域、可带扩展的 host_permissions；
// - 写剪贴板：navigator.clipboard 在 service worker 中不可用，必须注入到**页面上下文**执行，
//   且要求文档真正获得焦点（用户手势/真实焦点），否则报 NotAllowedError: Document is not focused。
//
// 因此本执行器的流程是：background fetch 字节 -> 注入页面写剪贴板。
//
// 注意：注入函数（writeFromUrlFn / writeFn）必须自包含，不能引用本模块作用域内的任何变量。

import { cmdError } from "../command_router.js";

// 网关静态文件目录的路径前缀（相对路径补全时校验用）。
const UPLOADS_PATH = "/uploads/";

export class ClipboardExecutor {
  /**
   * 从 URL 读取文件内容并写入页面剪贴板（通用接口）。
   *
   * 拓扑说明：Agent 可能运行在 master 或任意子节点上，因此**读哪个地址由调用方决定**。
   * 传入完整绝对 URL（如 "https://<node-gateway>/uploads/xxx.png"）即可，
   * 主节点/子节点场景都能工作；扩展不做地址猜测。
   *
   * @param {object} p
   *   url      必填，文件地址。支持两种形式：
   *              - 绝对 URL（推荐），如 "https://<gateway>/uploads/xxx.png"；
   *              - 相对路径，如 "/uploads/xxx.png" —— 用当前已连接的网关补全（无连接时用配置的第一个）。
   *   as       可选，'blob'（默认，二进制，适用于图片）| 'text'（文本）
   *   mime     可选，as='blob' 时覆盖 MIME 类型（默认取响应 content-type）
   *   tab_id   可选，目标标签页（默认当前活动标签页）
   * @returns {Promise<{ok:boolean, url:string, mime:string|null, size:number, mode:string}>}
   */
  async writeFromUrl({ url, as, mime, tab_id }) {
    const raw = String(url || "").trim();
    if (!raw) throw cmdError("CLIPBOARD_INVALID", "url is required");

    const target = await this._resolveUrl(raw);
    const mode = as === "text" ? "text" : "blob";

    let resp;
    try {
      resp = await fetch(target, { credentials: "omit" });
    } catch (e) {
      throw cmdError(
        "CLIPBOARD_FETCH_FAILED",
        e && e.message ? e.message : String(e),
      );
    }
    if (!resp.ok) {
      throw cmdError(
        "CLIPBOARD_FETCH_FAILED",
        `HTTP ${resp.status} for ${target}`,
      );
    }

    const contentType = mime || resp.headers.get("content-type") || "";
    const buf = await resp.arrayBuffer();
    const bytes = new Uint8Array(buf);

    // 转 base64 传给页面（ArrayBuffer 虽可结构化克隆，但 base64 跨注入更稳妥一致）。
    let b64 = "";
    const CHUNK = 0x8000;
    for (let i = 0; i < bytes.length; i += CHUNK) {
      b64 += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    b64 = btoa(b64);

    const tab = await this._resolveTab(tab_id);

    let results;
    try {
      results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: "MAIN",
        func: writeFromUrlFn,
        args: [b64, contentType, mode],
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
      const reason = (out && out.error) || "clipboard write failed";
      throw cmdError("CLIPBOARD_WRITE_FAILED", reason);
    }

    return {
      ok: true,
      url: target,
      mime: contentType || null,
      size: bytes.length,
      mode,
      tab_id: tab.id,
    };
  }

  /**
   * 直接把给定内容写入页面剪贴板（不经网关）。
   *
   * @param {object} p
   *   text     可选，要写入的文本（as='text' 时必填）
   *   base64   可选，要写入的二进制内容（base64，as='blob' 时必填）
   *   mime     可选，as='blob' 时的 MIME 类型（默认 image/png）
   *   as       可选，'text' | 'blob'（默认：有 text 用 text，否则 blob）
   *   tab_id   可选，目标标签页（默认当前活动标签页）
   */
  async write({ text, base64, mime, as, tab_id }) {
    const mode =
      as === "text" || (as == null && text != null) ? "text" : "blob";

    if (mode === "text") {
      if (text == null)
        throw cmdError("CLIPBOARD_INVALID", "text is required when as='text'");
    } else if (!base64) {
      throw cmdError("CLIPBOARD_INVALID", "base64 is required when as='blob'");
    }

    const tab = await this._resolveTab(tab_id);
    const payload = mode === "text" ? String(text) : String(base64);
    const contentType = mime || "image/png";

    let results;
    try {
      results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: "MAIN",
        func: writeFromUrlFn,
        args: [payload, contentType, mode],
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
      throw cmdError(
        "CLIPBOARD_WRITE_FAILED",
        (out && out.error) || "clipboard write failed",
      );
    }

    return {
      ok: true,
      mode,
      mime: mode === "blob" ? contentType : null,
      tab_id: tab.id,
    };
  }

  /**
   * 解析文件 URL。
   * - 绝对 URL：直接使用（不做 host 白名单限制，由调用方保证地址可信）；
   * - 相对路径：用配置的第一个网关补全。
   *
   * 注意：相对路径只是单网关下的便捷写法。Agent 运行在子节点等场景时，
   * 请直接传完整绝对 URL，避免补全到非预期网关。
   */
  async _resolveUrl(raw) {
    if (raw.startsWith("/")) {
      if (!raw.startsWith(UPLOADS_PATH)) {
        throw cmdError(
          "CLIPBOARD_INVALID",
          `相对路径仅支持 ${UPLOADS_PATH} 前缀: ${raw}`,
        );
      }
      const gateways = await this._loadGateways();
      if (!gateways.length) {
        throw cmdError(
          "CLIPBOARD_NO_GATEWAY",
          "未配置网关，无法补全相对路径；请传入完整 URL 或先在插件中配置网关",
        );
      }
      return gateways[0] + raw;
    }

    if (!/^https?:\/\//i.test(raw)) {
      throw cmdError("CLIPBOARD_INVALID", `url 必须是 http/https 地址: ${raw}`);
    }
    return raw;
  }

  /** 读取已配置的网关地址列表（规范化：去尾部斜杠）。 */
  async _loadGateways() {
    const cfg = await chrome.storage.local.get(["gateways"]);
    const list = Array.isArray(cfg.gateways) ? cfg.gateways : [];
    return list
      .map((g) =>
        String(g || "")
          .trim()
          .replace(/\/+$/, ""),
      )
      .filter((g) => /^https?:\/\//i.test(g));
  }

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
 * 注入到页面主世界的函数（必须自包含）。
 *
 * payload 语义随 mode 变化：
 *   mode='text' -> payload 是要写入的文本
 *   mode='blob' -> payload 是 base64 编码的二进制内容，mime 为其 MIME 类型
 *
 * @param {string} payload
 * @param {string} mime
 * @param {string} mode 'text' | 'blob'
 * @returns {Promise<{ok:boolean, error?:string, size?:number}>}
 */
async function writeFromUrlFn(payload, mime, mode) {
  try {
    if (!navigator.clipboard) {
      return { ok: false, error: "navigator.clipboard 不可用" };
    }
    if (!document.hasFocus()) {
      return {
        ok: false,
        error:
          "文档未获得焦点（Document is not focused）；请先激活标签页并派发一次真实点击后再写剪贴板",
      };
    }

    if (mode === "text") {
      await navigator.clipboard.writeText(payload);
      return { ok: true, size: payload.length };
    }

    if (typeof ClipboardItem !== "function") {
      return { ok: false, error: "ClipboardItem 不可用" };
    }

    const bin = atob(payload);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const blob = new Blob([bytes], {
      type: mime || "application/octet-stream",
    });

    await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
    return { ok: true, size: blob.size };
  } catch (e) {
    return { ok: false, error: e && e.message ? e.message : String(e) };
  }
}

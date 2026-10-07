// 捕获执行器：截图等。

import { cmdError } from "../command_router.js";

export class CaptureExecutor {
  /**
   * 截取指定标签页。
   * - 普通截图：截取当前视口 PNG，上传到命令来源网关，返回可访问的完整 URL。
   * - 整页截图：滚动拼接，上传后返回 { url, width, height, full_page }。
   *
   * 设计背景：截图 base64 若直接回传给 Agent 会撑爆 LLM 上下文，故扩展把截图
   * 上传到「调用该命令的 Agent 所在网关」（= 命令来源 gateway，见 ctx），网关
   * 保存后返回 URL 路径，Agent 用 add_images 加载识图。
   */
  async screenshot({ tab_id, full_page }, ctx = {}) {
    const tab = await this._resolveTab(tab_id);
    try {
      if (full_page) {
        const shot = await this._captureFullPage(tab);
        const url = await this._uploadToGateway(shot.image, ctx);
        return { url, width: shot.width, height: shot.height, full_page: true };
      }
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
        format: "png",
      });
      const image = this._strip(dataUrl);
      return await this._uploadToGateway(image, ctx);
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      if (/Cannot access|chrome:\/\//i.test(msg)) {
        throw cmdError("PROTECTED_PAGE", msg);
      }
      throw cmdError("EXEC_ERROR", msg);
    }
  }
  /**
   * 把截图 base64 上传到命令来源网关的 /upload 端点，返回可访问的完整 URL。
   *
   * 复用网关现有的 /upload 端点（_handle_file_upload）：接收 { file_name, file_data }
   * 并自动生成唯一文件名，保存到网关 uploads 目录，返回相对 URL /uploads/xxx.png。
   * 扩展再拼上命令来源网关地址，得到对 Agent 一定可达的完整 URL。
   *
   * @param {string} imageBase64 PNG 的 base64（不含 data: 前缀）
   * @param {object} ctx 执行上下文，含 gateway 与 token
   * @returns {Promise<string>} 完整可访问的图片 URL
   */
  async _uploadToGateway(imageBase64, ctx = {}) {
    const gateway = String(ctx.gateway || "").trim();
    if (!gateway) {
      throw cmdError(
        "NO_GATEWAY",
        "缺少命令来源网关地址，无法上传截图。请通过网关下发 capture.screenshot。",
      );
    }
    const token = String(ctx.token || "").trim();
    const url = `${gateway}/api/node/master/upload`;
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        file_name: "screenshot.png",
        file_data: imageBase64,
      }),
    });
    let body = null;
    try {
      body = await resp.json();
    } catch (e) {
      body = null;
    }
    if (!resp.ok || !body || !body.success) {
      const errMsg =
        (body && (body.error || body.detail)) ||
        `HTTP ${resp.status}`;
      throw cmdError(
        "UPLOAD_FAILED",
        `截图上传到网关失败（${gateway}）：${
          typeof errMsg === "string" ? errMsg : JSON.stringify(errMsg)
        }`,
      );
    }
    const fileUrl = body.data && body.data.file_url;
    if (!fileUrl) {
      throw cmdError("UPLOAD_FAILED", "网关未返回截图 URL");
    }
    // /upload 返回相对 URL（/uploads/xxx.png），拼上命令来源网关得到完整 URL。
    // 网关即 Agent 的 master_url 网关，Agent 通过该地址访问，故 URL 一定可达。
    return `${gateway}${String(fileUrl).startsWith("/") ? "" : "/"}${fileUrl}`;
  }

  /**
   * 整页截图：通过滚动视口逐屏截取，再在离屏 canvas 上拼接。
   * 需要标签页处于活动状态（captureVisibleTab 只能截当前可见标签页）。
   */
  async _captureFullPage(tab) {
    const tabId = tab.id;

    // 1. 读取页面尺寸与当前滚动位置
    const metrics = await this._exec(tabId, () => {
      const doc = document.documentElement;
      const body = document.body;
      const width = Math.max(
        doc ? doc.scrollWidth : 0,
        body ? body.scrollWidth : 0,
        doc ? doc.clientWidth : 0,
      );
      const height = Math.max(
        doc ? doc.scrollHeight : 0,
        body ? body.scrollHeight : 0,
        doc ? doc.clientHeight : 0,
      );
      return {
        width,
        height,
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        scroll_x: window.scrollX,
        scroll_y: window.scrollY,
      };
    });

    const pageWidth = Math.max(1, Math.floor(metrics.width));
    const pageHeight = Math.max(1, Math.floor(metrics.height));
    const viewportWidth = Math.max(1, Math.floor(metrics.viewport_width));
    const viewportHeight = Math.max(1, Math.floor(metrics.viewport_height));

    // 单屏即可容纳整页时直接截一次
    if (pageHeight <= viewportHeight) {
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
        format: "png",
      });
      return {
        image: this._strip(dataUrl),
        width: viewportWidth,
        height: viewportHeight,
        full_page: true,
      };
    }

    // 2. 逐屏滚动截图
    const shots = [];
    const maxShots = 50; // 安全上限，避免超长页面无限循环
    let y = 0;
    let guard = 0;
    while (y < pageHeight && guard < maxShots) {
      guard += 1;
      await this._exec(
        tabId,
        (top) => {
          window.scrollTo(0, top);
        },
        [y],
      );
      // 等待渲染稳定
      await new Promise((r) => setTimeout(r, 120));
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
        format: "png",
      });
      shots.push({ y, image: this._strip(dataUrl) });
      y += viewportHeight;
    }

    // 3. 恢复原滚动位置
    await this._exec(
      tabId,
      (pos) => {
        window.scrollTo(pos.x, pos.y);
      },
      [{ x: metrics.scroll_x, y: metrics.scroll_y }],
    );

    // 4. 拼接（在扩展页面上下文中用 OffscreenCanvas）
    const merged = await this._stitch(
      shots,
      pageWidth,
      pageHeight,
      viewportWidth,
    );
    return {
      image: merged,
      width: pageWidth,
      height: pageHeight,
      full_page: true,
    };
  }

  /** 在扩展上下文中用 OffscreenCanvas 拼接多张 PNG。 */
  async _stitch(shots, pageWidth, pageHeight, viewportWidth) {
    const canvas = new OffscreenCanvas(pageWidth, pageHeight);
    const ctx = canvas.getContext("2d");
    for (const shot of shots) {
      const blob = await (
        await fetch(`data:image/png;base64,${shot.image}`)
      ).blob();
      const bitmap = await createImageBitmap(blob);
      const drawWidth = Math.min(viewportWidth, pageWidth);
      ctx.drawImage(
        bitmap,
        0,
        0,
        drawWidth,
        bitmap.height,
        0,
        shot.y,
        drawWidth,
        bitmap.height,
      );
      bitmap.close();
    }
    const outBlob = await canvas.convertToBlob({ type: "image/png" });
    const buf = await outBlob.arrayBuffer();
    return this._bytesToBase64(new Uint8Array(buf));
  }

  /** 在指定标签页主世界执行函数并返回结果。 */
  async _exec(tabId, func, args = []) {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func,
      args,
      world: "MAIN",
    });
    return results && results[0] ? results[0].result : null;
  }

  _bytesToBase64(bytes) {
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }

  _strip(dataUrl) {
    if (typeof dataUrl !== "string") return null;
    const idx = dataUrl.indexOf(",");
    return idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
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
}

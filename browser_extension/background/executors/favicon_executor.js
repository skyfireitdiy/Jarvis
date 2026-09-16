// 图标执行器：封装 chrome.favicon 相关操作。
import { cmdError } from "../command_router.js";

export class FaviconExecutor {
  /** 获取指定页面的 favicon 地址。 */
  async getUrl({ page_url, size } = {}) {
    if (!chrome.favicon) {
      throw cmdError("NOT_SUPPORTED", "chrome.favicon is not available");
    }
    if (!page_url) throw cmdError("EXEC_ERROR", "page_url is required");
    const options = { pageUrl: String(page_url) };
    if (size != null) options.size = Number(size);
    const url = await chrome.favicon.getUrl(options);
    return { ok: true, favicon_url: url ?? null };
  }
}

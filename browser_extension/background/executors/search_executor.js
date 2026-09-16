// 搜索执行器：封装 chrome.search 相关操作。
import { cmdError } from "../command_router.js";

export class SearchExecutor {
  /**
   * 使用浏览器默认搜索引擎发起搜索。
   * 参数：query（搜索词，必填）、tab_id（可选，在指定标签页打开）、disposition（可选）。
   */
  async query({ query, tab_id, disposition } = {}) {
    if (!chrome.search) {
      throw cmdError("NOT_SUPPORTED", "chrome.search is not available");
    }
    if (!query) throw cmdError("EXEC_ERROR", "query is required");
    const options = { text: String(query) };
    if (tab_id != null) options.tabId = Number(tab_id);
    if (disposition) options.disposition = String(disposition);
    await chrome.search.query(options);
    return { ok: true, query: String(query) };
  }
}

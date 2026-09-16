// 历史记录执行器：封装 chrome.history 相关操作。
import { cmdError } from "../command_router.js";

export class HistoryExecutor {
  /**
   * 查询历史记录。
   * 参数：query（关键字，可选）、start_time / end_time（毫秒时间戳，可选）、
   *      max_results（默认 100）。
   */
  async search({ query, start_time, end_time, max_results } = {}) {
    const detail = {
      text: query ? String(query) : "",
      startTime: start_time != null ? Number(start_time) : 0,
      endTime: end_time != null ? Number(end_time) : Date.now(),
      maxResults: max_results != null ? Number(max_results) : 100,
    };
    const items = await chrome.history.search(detail);
    return items.map((h) => this._toItem(h));
  }

  /** 按访问时间倒序取最近 max_results 条历史记录。 */
  async recent({ max_results } = {}) {
    const items = await chrome.history.search({
      text: "",
      startTime: 0,
      endTime: Date.now(),
      maxResults: max_results != null ? Number(max_results) : 50,
    });
    items.sort((a, b) => (b.lastVisitTime || 0) - (a.lastVisitTime || 0));
    return items.map((h) => this._toItem(h));
  }

  /** 删除指定 URL 的全部历史记录（不可逆）。 */
  async remove({ url } = {}) {
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    await chrome.history.deleteUrl({ url: String(url) });
    return { ok: true, url: String(url) };
  }

  /** 删除时间区间内的历史记录（不可逆）；不传时间则清空全部历史。 */
  async removeRange({ start_time, end_time } = {}) {
    const range = {
      startTime: start_time != null ? Number(start_time) : 0,
      endTime: end_time != null ? Number(end_time) : Date.now(),
    };
    await chrome.history.deleteRange(range);
    return { ok: true, ...range };
  }

  /** 把 chrome 历史项转换为对外结构。 */
  _toItem(item) {
    return {
      id: item.id ?? null,
      url: item.url ?? null,
      title: item.title ?? "",
      last_visit_time: item.lastVisitTime ?? null,
      visit_count: item.visitCount ?? 0,
      typed_count: item.typedCount ?? 0,
    };
  }
}

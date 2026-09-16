// 阅读列表执行器：封装 chrome.readingList 相关操作。
import { cmdError } from "../command_router.js";

export class ReadingListExecutor {
  /** 列出阅读列表条目。 */
  async list() {
    this._ensureSupported();
    const entries = await chrome.readingList.query({});
    return entries.map((e) => this._toItem(e));
  }

  /** 添加条目到阅读列表。 */
  async add({ url, title, has_been_read } = {}) {
    this._ensureSupported();
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    await chrome.readingList.addEntry({
      url: String(url),
      title: title || String(url),
      hasBeenRead: Boolean(has_been_read),
    });
    return { ok: true, url: String(url) };
  }

  /** 从阅读列表移除条目（不可逆）。 */
  async remove({ url } = {}) {
    this._ensureSupported();
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    await chrome.readingList.removeEntry({ url: String(url) });
    return { ok: true, url: String(url) };
  }

  /** 更新条目的已读状态或标题。 */
  async update({ url, has_been_read, title } = {}) {
    this._ensureSupported();
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    const info = { url: String(url) };
    if (has_been_read != null) info.hasBeenRead = Boolean(has_been_read);
    if (title) info.title = String(title);
    await chrome.readingList.updateEntry(info);
    return { ok: true, url: String(url) };
  }

  /** 检查 API 是否可用（仅 Chrome 120+ 支持）。 */
  _ensureSupported() {
    if (!chrome.readingList) {
      throw cmdError("NOT_SUPPORTED", "chrome.readingList is not available");
    }
  }

  /** 把阅读列表条目转换为对外结构。 */
  _toItem(entry) {
    return {
      url: entry.url ?? "",
      title: entry.title ?? "",
      has_been_read: Boolean(entry.hasBeenRead),
      creation_time: entry.creationTime ?? null,
      last_update_time: entry.lastUpdateTime ?? null,
    };
  }
}

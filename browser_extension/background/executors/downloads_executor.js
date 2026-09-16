// 下载执行器：封装 chrome.downloads 相关操作。
import { cmdError } from "../command_router.js";

export class DownloadsExecutor {
  /** 查询下载项。可选 query（搜索关键字）、limit（默认 50）。 */
  async list({ query, limit } = {}) {
    const items = await chrome.downloads.search({
      query: query ? [String(query)] : undefined,
      limit: limit != null ? Number(limit) : 50,
      orderBy: ["-startTime"],
    });
    return items.map((d) => this._toItem(d));
  }

  /** 按文件名/URL 搜索下载项。 */
  async search({ query, limit } = {}) {
    if (!query) throw cmdError("EXEC_ERROR", "query is required");
    const items = await chrome.downloads.search({
      query: [String(query)],
      limit: limit != null ? Number(limit) : 50,
      orderBy: ["-startTime"],
    });
    return items.map((d) => this._toItem(d));
  }

  /** 发起下载。 */
  async download({ url, filename, save_as } = {}) {
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    const options = { url: String(url) };
    if (filename) options.filename = String(filename);
    if (save_as) options.saveAs = true;
    const downloadId = await chrome.downloads.download(options);
    return { ok: true, download_id: downloadId };
  }

  /** 暂停下载。 */
  async pause({ download_id } = {}) {
    const id = this._requireId(download_id);
    await chrome.downloads.pause(id);
    return { ok: true, download_id: id };
  }

  /** 恢复下载。 */
  async resume({ download_id } = {}) {
    const id = this._requireId(download_id);
    await chrome.downloads.resume(id);
    return { ok: true, download_id: id };
  }

  /** 取消下载。 */
  async cancel({ download_id } = {}) {
    const id = this._requireId(download_id);
    await chrome.downloads.cancel(id);
    return { ok: true, download_id: id };
  }

  /** 从下载列表移除记录（不可逆，delete_file 为 true 时同时删除本地文件）。 */
  async erase({ download_id, delete_file } = {}) {
    const id = this._requireId(download_id);
    await chrome.downloads.erase({ id });
    if (delete_file) {
      await chrome.downloads.removeFile(id);
    }
    return { ok: true, download_id: id, file_removed: Boolean(delete_file) };
  }

  /** 打开已下载的文件。 */
  async open({ download_id } = {}) {
    const id = this._requireId(download_id);
    await chrome.downloads.open(id);
    return { ok: true, download_id: id };
  }

  /** 校验并返回下载项 ID。 */
  _requireId(download_id) {
    if (download_id == null) {
      throw cmdError("NO_ID", "download_id is required");
    }
    return Number(download_id);
  }

  /** 把 chrome 下载项转换为对外结构。 */
  _toItem(item) {
    return {
      id: item.id ?? null,
      filename: item.filename ?? "",
      url: item.url ?? "",
      final_url: item.finalUrl ?? "",
      state: item.state ?? "",
      bytes_received: item.bytesReceived ?? 0,
      total_bytes: item.totalBytes ?? 0,
      paused: Boolean(item.paused),
      error: item.error ?? null,
      start_time: item.startTime ?? null,
      end_time: item.endTime ?? null,
      mime: item.mime ?? "",
      exists: item.exists ?? null,
    };
  }
}

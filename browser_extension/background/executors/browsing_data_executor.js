// 浏览数据执行器：封装 chrome.browsingData 相关操作。
//
// ⚠️ 高敏感权限：可清空用户的浏览历史、缓存、Cookie、密码、表单数据等。
// remove 属不可逆操作，一旦执行数据无法恢复，调用前必须向用户确认。
import { cmdError } from "../command_router.js";

export class BrowsingDataExecutor {
  /** 查询可清理的数据类型（各类型是否有数据）。 */
  async settings() {
    this._ensureSupported();
    const result = await chrome.browsingData.settings();
    return {
      options: result.options ?? {},
      data_to_remove: result.dataToRemove ?? {},
      data_removal_permitted: Boolean(result.dataRemovalPermitted),
    };
  }

  /**
   * 清除浏览数据（高敏感，不可逆）。
   * 需 data_types（数组，如 ["cache","cookies","history","downloads","formData",
   * "passwords","serviceWorkers","localStorage"]）；
   * 可选 since（毫秒时间戳，不传则清除全部）。
   */
  async remove({ data_types, since } = {}) {
    this._ensureSupported();
    if (!Array.isArray(data_types) || !data_types.length) {
      throw cmdError("EXEC_ERROR", "data_types is required (non-empty array)");
    }
    const options = {};
    data_types.forEach((t) => {
      options[String(t)] = true;
    });
    const removalOptions = {};
    if (since != null) removalOptions.since = Number(since);
    await chrome.browsingData.remove(removalOptions, options);
    return {
      ok: true,
      data_types: data_types.map(String),
      since: since ?? null,
    };
  }

  /** 检查 API 是否可用。 */
  _ensureSupported() {
    if (!chrome.browsingData) {
      throw cmdError("NOT_SUPPORTED", "chrome.browsingData is not available");
    }
  }
}

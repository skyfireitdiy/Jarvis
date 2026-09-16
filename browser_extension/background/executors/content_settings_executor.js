// 内容设置执行器：封装 chrome.contentSettings 相关操作。
//
// ⚠️ 高敏感权限：可修改站点级的内容权限（Cookie、JavaScript、图片、弹窗、
// 地理位置、摄像头/麦克风等）。set 会真实改动用户的安全与隐私设置，
// 属高风险操作，调用前必须向用户确认。
import { cmdError } from "../command_router.js";

export class ContentSettingsExecutor {
  /**
   * 读取内容设置。
   * 需 content_type（如 cookies/javascript/images/popups/geolocation）；
   * 可选 primary_url、secondary_url（不传则返回全局默认值）。
   */
  async get({ content_type, primary_url, secondary_url } = {}) {
    const setting = this._resolveSetting(content_type);
    const details = {};
    if (primary_url) details.primaryUrl = String(primary_url);
    if (secondary_url) details.secondaryUrl = String(secondary_url);
    const result = await setting.get(details);
    return {
      content_type: String(content_type),
      setting: result.setting ?? null,
      primary_pattern: result.primaryPattern ?? null,
      secondary_pattern: result.secondaryPattern ?? null,
    };
  }

  /** 修改内容设置（高敏感）。需 content_type、setting（如 allow/block/ask）。 */
  async set({
    content_type,
    setting: value,
    primary_pattern,
    secondary_pattern,
  } = {}) {
    const setting = this._resolveSetting(content_type);
    if (value === undefined)
      throw cmdError("EXEC_ERROR", "setting is required");
    const details = { setting: value };
    if (primary_pattern) details.primaryPattern = String(primary_pattern);
    if (secondary_pattern) details.secondaryPattern = String(secondary_pattern);
    await setting.set(details);
    return { ok: true, content_type: String(content_type), setting: value };
  }

  /** 清除内容设置，恢复默认。需 content_type。 */
  async clear({ content_type } = {}) {
    const setting = this._resolveSetting(content_type);
    await setting.clear({});
    return { ok: true, content_type: String(content_type) };
  }

  /** 解析 content_type 对应的 chrome.contentSettings 设置对象。 */
  _resolveSetting(content_type) {
    if (!chrome.contentSettings) {
      throw cmdError(
        "NOT_SUPPORTED",
        "chrome.contentSettings is not available",
      );
    }
    if (!content_type) throw cmdError("EXEC_ERROR", "content_type is required");
    const setting = chrome.contentSettings[String(content_type)];
    if (!setting || typeof setting.set !== "function") {
      throw cmdError("EXEC_ERROR", `unknown content setting: ${content_type}`);
    }
    return setting;
  }
}

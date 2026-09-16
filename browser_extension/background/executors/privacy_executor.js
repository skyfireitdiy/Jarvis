// 隐私设置执行器：封装 chrome.privacy 相关操作。
//
// ⚠️ 高敏感权限：可修改浏览器的隐私相关开关（如是否允许第三方 Cookie、
// 是否启用安全浏览、是否允许发送统计等）。set 会真实改动用户隐私配置，
// 属高风险操作，调用前必须向用户确认。
import { cmdError } from "../command_router.js";

export class PrivacyExecutor {
  /**
   * 读取隐私设置。
   * 需 area（network/services/websites）与 name（设置项名，如 networkPredictionEnabled）。
   */
  async get({ area, name } = {}) {
    const setting = this._resolveSetting(area, name);
    const result = await setting.get({});
    return {
      area: String(area),
      name: String(name),
      value: result.value ?? null,
      level_of_control: result.levelOfControl ?? "",
    };
  }

  /** 修改隐私设置（高敏感）。 */
  async set({ area, name, value } = {}) {
    const setting = this._resolveSetting(area, name);
    if (value === undefined) throw cmdError("EXEC_ERROR", "value is required");
    await setting.set({ value, scope: "regular" });
    return { ok: true, area: String(area), name: String(name), value };
  }

  /** 解析 area/name 对应的 chrome.privacy 设置对象。 */
  _resolveSetting(area, name) {
    if (!chrome.privacy) {
      throw cmdError("NOT_SUPPORTED", "chrome.privacy is not available");
    }
    if (!area) throw cmdError("EXEC_ERROR", "area is required");
    if (!name) throw cmdError("EXEC_ERROR", "name is required");
    const group = chrome.privacy[String(area)];
    if (!group) {
      throw cmdError("EXEC_ERROR", `unknown privacy area: ${area}`);
    }
    const setting = group[String(name)];
    if (!setting || typeof setting.set !== "function") {
      throw cmdError("EXEC_ERROR", `unknown privacy setting: ${area}.${name}`);
    }
    return setting;
  }
}

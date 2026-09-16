// 代理执行器：封装 chrome.proxy 相关操作。
//
// ⚠️ 高敏感权限：可修改浏览器全局代理设置，等同于劫持用户的全部网络流量。
// set/clear 会真实改动用户的上网配置，属高风险操作，调用前必须向用户确认。
import { cmdError } from "../command_router.js";

export class ProxyExecutor {
  /** 读取当前代理配置。 */
  async getSettings() {
    this._ensureSupported();
    const config = await chrome.proxy.settings.get({});
    return {
      level_of_control: config.levelOfControl ?? "",
      value: config.value ?? null,
    };
  }

  /**
   * 设置代理（高敏感）。
   * 需 mode（direct/auto_detect/pac_script/system/fixed_servers）；
   * mode 为 pac_script 时需 pac_url，为 fixed_servers 时需 rules。
   */
  async setSettings({ mode, pac_url, rules } = {}) {
    this._ensureSupported();
    if (!mode) throw cmdError("EXEC_ERROR", "mode is required");
    const value = { mode: String(mode) };
    if (mode === "pac_script") {
      if (!pac_url)
        throw cmdError("EXEC_ERROR", "pac_url is required for pac_script mode");
      value.pacScript = { url: String(pac_url) };
    }
    if (mode === "fixed_servers") {
      if (!rules)
        throw cmdError(
          "EXEC_ERROR",
          "rules is required for fixed_servers mode",
        );
      value.rules = rules;
    }
    await chrome.proxy.settings.set({ value, scope: "regular" });
    return { ok: true, mode: String(mode) };
  }

  /** 清除代理配置，恢复为系统默认。 */
  async clearSettings() {
    this._ensureSupported();
    await chrome.proxy.settings.clear({ scope: "regular" });
    return { ok: true };
  }

  /** 检查 API 是否可用。 */
  _ensureSupported() {
    if (!chrome.proxy) {
      throw cmdError("NOT_SUPPORTED", "chrome.proxy is not available");
    }
  }
}

// 扩展管理执行器：封装 chrome.management 相关操作。
//
// ⚠️ 高敏感权限：可枚举、启用/禁用甚至卸载用户已安装的其他扩展。
// setEnabled/uninstall 会真实改动用户的浏览器环境，属高风险操作，调用前必须向用户确认。
import { cmdError } from "../command_router.js";

export class ManagementExecutor {
  /** 列出全部已安装扩展与应用。 */
  async list() {
    this._ensureSupported();
    const items = await chrome.management.getAll();
    return items.map((i) => this._toItem(i));
  }

  /** 获取指定扩展的详细信息。 */
  async get({ extension_id } = {}) {
    this._ensureSupported();
    if (!extension_id) throw cmdError("NO_ID", "extension_id is required");
    const item = await chrome.management.get(String(extension_id));
    return this._toItem(item);
  }

  /** 启动指定应用（仅 type 为 hosted_app 等应用有效）。 */
  async launchApp({ extension_id } = {}) {
    this._ensureSupported();
    if (!extension_id) throw cmdError("NO_ID", "extension_id is required");
    await chrome.management.launchApp(String(extension_id));
    return { ok: true, extension_id: String(extension_id) };
  }

  /** 启用/禁用指定扩展（高敏感）。 */
  async setEnabled({ extension_id, enabled } = {}) {
    this._ensureSupported();
    if (!extension_id) throw cmdError("NO_ID", "extension_id is required");
    await chrome.management.setEnabled(String(extension_id), Boolean(enabled));
    return {
      ok: true,
      extension_id: String(extension_id),
      enabled: Boolean(enabled),
    };
  }

  /** 卸载指定扩展（高敏感，不可逆）。 */
  async uninstall({ extension_id } = {}) {
    this._ensureSupported();
    if (!extension_id) throw cmdError("NO_ID", "extension_id is required");
    await chrome.management.uninstall(String(extension_id));
    return { ok: true, extension_id: String(extension_id) };
  }

  /** 检查 API 是否可用。 */
  _ensureSupported() {
    if (!chrome.management) {
      throw cmdError("NOT_SUPPORTED", "chrome.management is not available");
    }
  }

  /** 把 chrome 扩展信息转换为对外结构。 */
  _toItem(item) {
    return {
      id: item.id ?? "",
      name: item.name ?? "",
      version: item.version ?? "",
      description: item.description ?? "",
      enabled: Boolean(item.enabled),
      type: item.type ?? "",
      may_disable: Boolean(item.mayDisable),
      install_type: item.installType ?? "",
      homepage_url: item.homepageUrl ?? null,
    };
  }
}

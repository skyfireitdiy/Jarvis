// 标签组执行器：封装 chrome.tabGroups 相关操作。
import { cmdError } from "../command_router.js";

export class TabGroupsExecutor {
  /** 列出全部标签组。 */
  async list() {
    this._ensureSupported();
    const groups = await chrome.tabGroups.query({});
    return groups.map((g) => this._toGroup(g));
  }

  /** 获取指定标签组。 */
  async get({ group_id } = {}) {
    this._ensureSupported();
    if (group_id == null) throw cmdError("NO_ID", "group_id is required");
    const group = await chrome.tabGroups.get(Number(group_id));
    return this._toGroup(group);
  }

  /** 按条件查询标签组（如 title、color、window_id）。 */
  async query({ title, color, window_id } = {}) {
    this._ensureSupported();
    const info = {};
    if (title) info.title = String(title);
    if (color) info.color = String(color);
    if (window_id != null) info.windowId = Number(window_id);
    const groups = await chrome.tabGroups.query(info);
    return groups.map((g) => this._toGroup(g));
  }

  /** 更新标签组属性（标题、颜色、折叠状态）。 */
  async update({ group_id, title, color, collapsed } = {}) {
    this._ensureSupported();
    if (group_id == null) throw cmdError("NO_ID", "group_id is required");
    const props = {};
    if (title) props.title = String(title);
    if (color) props.color = String(color);
    if (collapsed != null) props.collapsed = Boolean(collapsed);
    const group = await chrome.tabGroups.update(Number(group_id), props);
    return { ok: true, group: this._toGroup(group) };
  }

  /** 检查 API 是否可用。 */
  _ensureSupported() {
    if (!chrome.tabGroups) {
      throw cmdError("NOT_SUPPORTED", "chrome.tabGroups is not available");
    }
  }

  /** 把 chrome 标签组转换为对外结构。 */
  _toGroup(group) {
    return {
      group_id: group.id ?? null,
      title: group.title ?? "",
      color: group.color ?? "",
      collapsed: Boolean(group.collapsed),
      window_id: group.windowId ?? null,
    };
  }
}

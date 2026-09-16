// 通知执行器：封装 chrome.notifications 相关操作。
import { cmdError } from "../command_router.js";

export class NotificationsExecutor {
  /** 创建系统通知。 */
  async create({ notification_id, title, message, icon_url } = {}) {
    if (!notification_id)
      throw cmdError("NO_ID", "notification_id is required");
    if (!title) throw cmdError("EXEC_ERROR", "title is required");
    const options = {
      type: "basic",
      title: String(title),
      message: message ? String(message) : "",
      iconUrl: icon_url || "icons/icon128.png",
    };
    const id = await chrome.notifications.create(
      String(notification_id),
      options,
    );
    return { ok: true, notification_id: id };
  }

  /** 清除指定通知。 */
  async clear({ notification_id } = {}) {
    if (!notification_id)
      throw cmdError("NO_ID", "notification_id is required");
    const cleared = await chrome.notifications.clear(String(notification_id));
    return { ok: true, notification_id: String(notification_id), cleared };
  }

  /** 清除全部通知。 */
  async clearAll() {
    await chrome.notifications.getAll().then(async (all) => {
      await Promise.all(
        Object.keys(all || {}).map((id) => chrome.notifications.clear(id)),
      );
    });
    return { ok: true };
  }

  /** 列出当前显示中的通知。 */
  async getAll() {
    const all = await chrome.notifications.getAll();
    return Object.entries(all || {}).map(([id, options]) => ({
      notification_id: id,
      title: options?.title ?? "",
      message: options?.message ?? "",
      type: options?.type ?? "",
    }));
  }
}

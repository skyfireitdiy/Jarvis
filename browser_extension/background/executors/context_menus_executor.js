// 右键菜单执行器：封装 chrome.contextMenus 相关操作。
// 注意：contextMenus 创建后需由用户右键点击触发，本执行器只负责注册/查询/移除菜单项。
import { cmdError } from "../command_router.js";

export class ContextMenusExecutor {
  /** 创建右键菜单项。 */
  async create({ menu_id, title, contexts, url_patterns } = {}) {
    if (!menu_id) throw cmdError("NO_ID", "menu_id is required");
    if (!title) throw cmdError("EXEC_ERROR", "title is required");
    const createProps = {
      id: String(menu_id),
      title: String(title),
      contexts:
        Array.isArray(contexts) && contexts.length ? contexts : ["page"],
    };
    if (Array.isArray(url_patterns) && url_patterns.length) {
      createProps.documentUrlPatterns = url_patterns;
    }
    chrome.contextMenus.create(createProps);
    return { ok: true, menu_id: String(menu_id) };
  }

  /** 移除指定菜单项。 */
  async remove({ menu_id } = {}) {
    if (!menu_id) throw cmdError("NO_ID", "menu_id is required");
    await chrome.contextMenus.remove(String(menu_id));
    return { ok: true, menu_id: String(menu_id) };
  }

  /** 移除全部菜单项。 */
  async removeAll() {
    await chrome.contextMenus.removeAll();
    return { ok: true };
  }

  /** 列出当前已注册的菜单项。 */
  async list() {
    // contextMenus 无直接列举 API，仅能通过 removeAll 清理；此处返回说明性结果。
    return {
      ok: true,
      note: "chrome.contextMenus 不提供列举 API，仅支持 create/remove/removeAll",
    };
  }
}

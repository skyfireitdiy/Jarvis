// 书签执行器：封装 chrome.bookmarks 相关操作。
import { cmdError } from "../command_router.js";

export class BookmarksExecutor {
  /**
   * 列出书签。
   * 默认返回整棵书签树；传 parent_id 时只返回该文件夹下的直接子节点。
   */
  async list({ parent_id } = {}) {
    if (parent_id != null) {
      const children = await chrome.bookmarks.getChildren(String(parent_id));
      return children.map((n) => this._toNode(n));
    }
    const tree = await chrome.bookmarks.getTree();
    return tree.map((n) => this._toNode(n, true));
  }

  /** 按标题或 URL 关键字搜索书签。 */
  async search({ query, max_results } = {}) {
    if (!query) throw cmdError("EXEC_ERROR", "query is required");
    const nodes = await chrome.bookmarks.search(String(query));
    const limited =
      max_results != null ? nodes.slice(0, Number(max_results)) : nodes;
    return limited.map((n) => this._toNode(n));
  }

  /**
   * 新增书签。
   * parent_id 为空时默认放到「其他书签」（id "2"）下。
   */
  async create({ title, url, parent_id } = {}) {
    if (!url) throw cmdError("EXEC_ERROR", "url is required");
    const node = await chrome.bookmarks.create({
      title: title || url,
      url: String(url),
      parentId: parent_id != null ? String(parent_id) : undefined,
    });
    return { ok: true, bookmark: this._toNode(node) };
  }

  /** 删除单个书签（不可逆）。 */
  async remove({ id } = {}) {
    if (id == null) throw cmdError("NO_ID", "id is required");
    await chrome.bookmarks.remove(String(id));
    return { ok: true, id: String(id) };
  }

  /** 删除书签文件夹及其全部子节点（不可逆）。 */
  async removeTree({ id } = {}) {
    if (id == null) throw cmdError("NO_ID", "id is required");
    await chrome.bookmarks.removeTree(String(id));
    return { ok: true, id: String(id) };
  }

  /** 把 chrome 书签节点转换为对外结构；with_children 为 true 时递归展开。 */
  _toNode(node, with_children = false) {
    const out = {
      id: node.id,
      parent_id: node.parentId ?? null,
      title: node.title ?? "",
      url: node.url ?? null,
      date_added: node.dateAdded ?? null,
      is_folder: node.url == null,
    };
    if (with_children && Array.isArray(node.children)) {
      out.children = node.children.map((c) => this._toNode(c, true));
    }
    return out;
  }
}

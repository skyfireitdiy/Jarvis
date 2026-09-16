// 会话执行器：封装 chrome.sessions 相关操作（最近关闭的标签页/窗口）。
import { cmdError } from "../command_router.js";

export class SessionsExecutor {
  /** 列出最近关闭的标签页与窗口。可选 max_results（默认 25）。 */
  async recent({ max_results } = {}) {
    const sessions = await chrome.sessions.getRecentlyClosed({
      maxResults: max_results != null ? Number(max_results) : 25,
    });
    return sessions.map((s) => this._toItem(s));
  }

  /**
   * 恢复指定的会话项。
   * session_id 为空时恢复最近一个关闭的标签页/窗口。
   */
  async restore({ session_id } = {}) {
    const session = await chrome.sessions.restore(
      session_id ? String(session_id) : undefined,
    );
    return { ok: true, session: this._toItem(session) };
  }

  /** 把 chrome 会话项转换为对外结构。 */
  _toItem(session) {
    if (!session) return null;
    const tab = session.tab
      ? {
          tab_id: session.tab.id ?? null,
          url: session.tab.url ?? "",
          title: session.tab.title ?? "",
        }
      : null;
    const win = session.window
      ? {
          window_id: session.window.id ?? null,
          tabs: session.window.tabs?.length ?? 0,
        }
      : null;
    return {
      session_id: session.tab?.sessionId ?? session.window?.sessionId ?? null,
      last_modified: session.lastModified ?? null,
      tab,
      window: win,
    };
  }
}

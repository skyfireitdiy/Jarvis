// 导航监听执行器：封装 chrome.webNavigation 相关操作（只读查询，不拦截）。
import { cmdError } from "../command_router.js";

export class WebNavigationExecutor {
  /** 列出指定标签页的全部 frame。 */
  async getAllFrames({ tab_id } = {}) {
    if (tab_id == null) throw cmdError("NO_TAB", "tab_id is required");
    const frames = await chrome.webNavigation.getAllFrames({
      tabId: Number(tab_id),
    });
    return (frames || []).map((f) => this._toFrame(f));
  }

  /** 获取指定 frame 的信息。 */
  async getFrame({ tab_id, frame_id } = {}) {
    if (tab_id == null) throw cmdError("NO_TAB", "tab_id is required");
    if (frame_id == null) throw cmdError("NO_ID", "frame_id is required");
    const frame = await chrome.webNavigation.getFrame({
      tabId: Number(tab_id),
      frameId: Number(frame_id),
    });
    return this._toFrame(frame);
  }

  /** 把 chrome frame 转换为对外结构。 */
  _toFrame(frame) {
    if (!frame) return null;
    return {
      frame_id: frame.frameId ?? null,
      parent_frame_id: frame.parentFrameId ?? null,
      url: frame.url ?? "",
      document_id: frame.documentId ?? null,
      error_occurred: Boolean(frame.errorOccurred),
    };
  }
}

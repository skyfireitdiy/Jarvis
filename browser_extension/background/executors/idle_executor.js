// 空闲状态执行器：封装 chrome.idle 相关操作。
import { cmdError } from "../command_router.js";

export class IdleExecutor {
  /** 查询当前空闲状态（active/idle/locked）。 */
  async queryState({ detection_interval_seconds } = {}) {
    const state = await chrome.idle.queryState(
      detection_interval_seconds != null
        ? Number(detection_interval_seconds)
        : 60,
    );
    return { state };
  }

  /** 设置空闲检测间隔（秒，最小 15）。 */
  async setInterval({ detection_interval_seconds } = {}) {
    if (detection_interval_seconds == null) {
      throw cmdError("EXEC_ERROR", "detection_interval_seconds is required");
    }
    chrome.idle.setDetectionInterval(Number(detection_interval_seconds));
    return {
      ok: true,
      detection_interval_seconds: Number(detection_interval_seconds),
    };
  }

  /** 读取空闲检测间隔（秒）。 */
  async getInterval() {
    const seconds = chrome.idle.getDetectionInterval();
    return { detection_interval_seconds: seconds };
  }
}

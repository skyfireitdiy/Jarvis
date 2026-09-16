// 定时任务执行器：封装 chrome.alarms 相关操作。
import { cmdError } from "../command_router.js";

export class AlarmsExecutor {
  /**
   * 创建定时任务。
   * 支持 delay_minutes（延迟触发一次）或 period_minutes（周期触发），至少提供一个。
   */
  async create({ name, delay_minutes, period_minutes } = {}) {
    if (!name) throw cmdError("EXEC_ERROR", "name is required");
    if (delay_minutes == null && period_minutes == null) {
      throw cmdError(
        "EXEC_ERROR",
        "delay_minutes or period_minutes is required",
      );
    }
    const info = { name: String(name) };
    if (delay_minutes != null) info.delayInMinutes = Number(delay_minutes);
    if (period_minutes != null) info.periodInMinutes = Number(period_minutes);
    await chrome.alarms.create(String(name), info);
    return { ok: true, name: String(name) };
  }

  /** 列出全部定时任务。 */
  async list() {
    const alarms = await chrome.alarms.getAll();
    return alarms.map((a) => ({
      name: a.name ?? "",
      scheduled_time: a.scheduledTime ?? null,
      period_in_minutes: a.periodInMinutes ?? null,
    }));
  }

  /** 清除指定定时任务。 */
  async clear({ name } = {}) {
    if (!name) throw cmdError("EXEC_ERROR", "name is required");
    const removed = await chrome.alarms.clear(String(name));
    return { ok: true, name: String(name), removed: Boolean(removed) };
  }

  /** 清除全部定时任务。 */
  async clearAll() {
    const removed = await chrome.alarms.clearAll();
    return { ok: true, removed: Boolean(removed) };
  }
}

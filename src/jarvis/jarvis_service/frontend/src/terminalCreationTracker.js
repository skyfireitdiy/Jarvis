// 终端创建"本设备发起"追踪器。
//
// 当本设备发送 terminal_create 后，terminal_created 回包到达时应自动切换到
// 新终端；而他端（admin/ACL 共享）广播来的 terminal_created 不应切换，避免
// 打断本设备当前工作流。本模块用一个带超时复位的标志来区分这两种情况。
export function createTerminalCreationTracker(timeoutMs = 10000) {
  let pending = false;
  let timer = null;

  return {
    // 本设备发起了终端创建，等待 terminal_created 回包
    mark() {
      pending = true;
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        pending = false;
        timer = null;
      }, timeoutMs);
    },
    // terminal_created 到达时调用：若本设备发起过创建则返回 true 并复位，
    // 否则返回 false（他端共享，不切换）
    shouldSwitch() {
      if (pending) {
        pending = false;
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
        return true;
      }
      return false;
    },
    isPending() {
      return pending;
    },
  };
}

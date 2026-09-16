// 本地通信执行器：封装 chrome.runtime.sendNativeMessage。
//
// ⚠️ 高敏感权限：可与本机已注册的 Native Messaging Host 通信，
// 等同让远端 Agent 间接调用本地程序。需用户预先在系统中注册 native host，
// 且 host 名必须在 manifest 的 nativeMessaging 白名单内（本扩展未固定 host，
// 由调用方传入，若浏览器拒绝则说明未注册或未授权）。
// 调用前必须向用户确认。
import { cmdError } from "../command_router.js";

export class NativeMessagingExecutor {
  /** 向指定 native host 发送一条消息并等待响应。 */
  async send({ native_host, message } = {}) {
    if (!chrome.runtime?.sendNativeMessage) {
      throw cmdError(
        "NOT_SUPPORTED",
        "chrome.runtime.sendNativeMessage is not available",
      );
    }
    if (!native_host) throw cmdError("EXEC_ERROR", "native_host is required");
    const payload = message != null ? message : {};
    const response = await chrome.runtime.sendNativeMessage(
      String(native_host),
      payload,
    );
    return {
      ok: true,
      native_host: String(native_host),
      response: response ?? null,
    };
  }
}

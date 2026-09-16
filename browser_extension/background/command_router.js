// 指令路由：把网关下发的 action 映射到对应执行器，并回传结果。
//
// 指令信封（网关 -> 插件）：
//   { id, type: "command", action: "dom.click", params: {...}, timeout_ms: 15000 }
// 结果信封（插件 -> 网关）：
//   { id, type: "result", success: true, data: {...}, error: null }

import { TabExecutor } from "./executors/tab_executor.js";
import { DomExecutor } from "./executors/dom_executor.js";
import { CaptureExecutor } from "./executors/capture_executor.js";
import { DebugExecutor } from "./executors/debug_executor.js";
import { ScriptExecutor } from "./executors/script_executor.js";

export class CommandRouter {
  constructor() {
    this.tabExecutor = new TabExecutor();
    this.domExecutor = new DomExecutor();
    this.captureExecutor = new CaptureExecutor();
    this.debugExecutor = new DebugExecutor();
    this.scriptExecutor = new ScriptExecutor();

    // action -> handler(params) => Promise<data>
    this.routes = {
      // 标签页类
      "tab.list": (p) => this.tabExecutor.list(p),
      "tab.activate": (p) => this.tabExecutor.activate(p),
      "tab.close": (p) => this.tabExecutor.close(p),
      "tab.create": (p) => this.tabExecutor.create(p),
      // 导航类
      "page.navigate": (p) => this.tabExecutor.navigate(p),
      "page.reload": (p) => this.tabExecutor.reload(p),
      "page.back": (p) => this.tabExecutor.back(p),
      "page.forward": (p) => this.tabExecutor.forward(p),
      "page.get_info": (p) => this.tabExecutor.getInfo(p),
      // DOM 类
      "dom.query": (p) => this.domExecutor.query(p),
      "dom.get_text": (p) => this.domExecutor.getText(p),
      "dom.get_html": (p) => this.domExecutor.getHtml(p),
      "dom.get_computed_style": (p) => this.domExecutor.getComputedStyle(p),
      "dom.click": (p) => this.domExecutor.click(p),
      "dom.type": (p) => this.domExecutor.type(p),
      "dom.hover": (p) => this.domExecutor.hover(p),
      "dom.select": (p) => this.domExecutor.select(p),
      "dom.wait_for": (p) => this.domExecutor.waitFor(p),
      "dom.press_key": (p) => this.domExecutor.pressKey(p),
      "dom.scroll": (p) => this.domExecutor.scroll(p),
      "dom.upload_file": (p) => this.domExecutor.uploadFile(p),
      "script.execute": (p) => this.domExecutor.execute(p),
      // 脚本管理类（类油猴：安装 / 管理 / 执行自定义页面脚本）
      "script.list": (p) => this.scriptExecutor.list(p),
      "script.get": (p) => this.scriptExecutor.get(p),
      "script.install": (p) => this.scriptExecutor.install(p),
      "script.uninstall": (p) => this.scriptExecutor.uninstall(p),
      "script.export": (p) => this.scriptExecutor.exportScript(p),
      "script.set_enabled": (p) => this.scriptExecutor.setEnabled(p),
      "script.run": (p) => this.scriptExecutor.run(p),
      // 调试类
      "console.get_logs": (p) => this.debugExecutor.getLogs(p),
      "debugger.evaluate": (p) => this.debugExecutor.evaluate(p),
      "debugger.send_command": (p) => this.debugExecutor.sendCommand(p),
      "network.get_requests": (p) => this.debugExecutor.getRequests(p),
      // 捕获类
      "capture.screenshot": (p) => this.captureExecutor.screenshot(p),
    };
  }

  /**
   * 执行一条指令，返回结果信封。
   * @param {object} msg 指令消息
   * @returns {Promise<object>} 结果信封
   */
  async handle(msg) {
    const id = msg?.id;
    const action = msg?.action;
    const params = msg?.params || {};

    const handler = this.routes[action];
    if (!handler) {
      return {
        id,
        type: "result",
        success: false,
        data: null,
        error: `unknown action: ${action}`,
      };
    }

    try {
      const data = await handler(params);
      return {
        id,
        type: "result",
        success: true,
        data: data ?? null,
        error: null,
      };
    } catch (e) {
      const code = e && e.code ? e.code : "EXEC_ERROR";
      const message = e && e.message ? e.message : String(e);
      return {
        id,
        type: "result",
        success: false,
        data: null,
        error: `${code}: ${message}`,
      };
    }
  }
}

/** 构造带错误码的异常。 */
export function cmdError(code, message) {
  const err = new Error(message);
  err.code = code;
  return err;
}

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
import { ClipboardExecutor } from "./executors/clipboard_executor.js";
import { BookmarksExecutor } from "./executors/bookmarks_executor.js";
import { HistoryExecutor } from "./executors/history_executor.js";
import { DownloadsExecutor } from "./executors/downloads_executor.js";
import { SessionsExecutor } from "./executors/sessions_executor.js";
import { TopSitesExecutor } from "./executors/top_sites_executor.js";
import { ReadingListExecutor } from "./executors/reading_list_executor.js";
import { ContextMenusExecutor } from "./executors/context_menus_executor.js";
import { AlarmsExecutor } from "./executors/alarms_executor.js";
import { NotificationsExecutor } from "./executors/notifications_executor.js";
import { SearchExecutor } from "./executors/search_executor.js";
import { IdleExecutor } from "./executors/idle_executor.js";
import { FaviconExecutor } from "./executors/favicon_executor.js";
import { WebNavigationExecutor } from "./executors/web_navigation_executor.js";
import { TabGroupsExecutor } from "./executors/tab_groups_executor.js";
import { CookiesExecutor } from "./executors/cookies_executor.js";
import { WebRequestExecutor } from "./executors/web_request_executor.js";
import { ManagementExecutor } from "./executors/management_executor.js";
import { NativeMessagingExecutor } from "./executors/native_messaging_executor.js";
import { ProxyExecutor } from "./executors/proxy_executor.js";
import { PrivacyExecutor } from "./executors/privacy_executor.js";
import { BrowsingDataExecutor } from "./executors/browsing_data_executor.js";
import { ContentSettingsExecutor } from "./executors/content_settings_executor.js";

export class CommandRouter {
  constructor() {
    this.tabExecutor = new TabExecutor();
    this.domExecutor = new DomExecutor();
    this.captureExecutor = new CaptureExecutor();
    this.debugExecutor = new DebugExecutor();
    this.scriptExecutor = new ScriptExecutor();
    this.clipboardExecutor = new ClipboardExecutor();
    this.bookmarksExecutor = new BookmarksExecutor();
    this.historyExecutor = new HistoryExecutor();
    this.downloadsExecutor = new DownloadsExecutor();
    this.sessionsExecutor = new SessionsExecutor();
    this.topSitesExecutor = new TopSitesExecutor();
    this.readingListExecutor = new ReadingListExecutor();
    this.contextMenusExecutor = new ContextMenusExecutor();
    this.alarmsExecutor = new AlarmsExecutor();
    this.notificationsExecutor = new NotificationsExecutor();
    this.searchExecutor = new SearchExecutor();
    this.idleExecutor = new IdleExecutor();
    this.faviconExecutor = new FaviconExecutor();
    this.webNavigationExecutor = new WebNavigationExecutor();
    this.tabGroupsExecutor = new TabGroupsExecutor();
    this.cookiesExecutor = new CookiesExecutor();
    this.webRequestExecutor = new WebRequestExecutor();
    this.managementExecutor = new ManagementExecutor();
    this.nativeMessagingExecutor = new NativeMessagingExecutor();
    this.proxyExecutor = new ProxyExecutor();
    this.privacyExecutor = new PrivacyExecutor();
    this.browsingDataExecutor = new BrowsingDataExecutor();
    this.contentSettingsExecutor = new ContentSettingsExecutor();

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
      "script.install_from_url": (p) => this.scriptExecutor.installFromUrl(p),
      "script.uninstall": (p) => this.scriptExecutor.uninstall(p),
      "script.export": (p) => this.scriptExecutor.exportScript(p),
      "script.set_enabled": (p) => this.scriptExecutor.setEnabled(p),
      "script.run": (p) => this.scriptExecutor.run(p),
      // 剪贴板类（把网关静态文件或给定内容写入前端剪贴板）
      "clipboard.write_from_url": (p) => this.clipboardExecutor.writeFromUrl(p),
      "clipboard.write": (p) => this.clipboardExecutor.write(p),
      // 调试类
      "console.get_logs": (p) => this.debugExecutor.getLogs(p),
      "debugger.evaluate": (p) => this.debugExecutor.evaluate(p),
      "debugger.send_command": (p) => this.debugExecutor.sendCommand(p),
      "network.get_requests": (p) => this.debugExecutor.getRequests(p),
      // 捕获类
      "capture.screenshot": (p) => this.captureExecutor.screenshot(p, ctx),
      // 书签类
      "bookmark.list": (p) => this.bookmarksExecutor.list(p),
      "bookmark.search": (p) => this.bookmarksExecutor.search(p),
      "bookmark.create": (p) => this.bookmarksExecutor.create(p),
      "bookmark.remove": (p) => this.bookmarksExecutor.remove(p),
      "bookmark.remove_tree": (p) => this.bookmarksExecutor.removeTree(p),
      // 历史记录类
      "history.search": (p) => this.historyExecutor.search(p),
      "history.recent": (p) => this.historyExecutor.recent(p),
      "history.remove": (p) => this.historyExecutor.remove(p),
      "history.remove_range": (p) => this.historyExecutor.removeRange(p),
      // 下载类
      "download.list": (p) => this.downloadsExecutor.list(p),
      "download.search": (p) => this.downloadsExecutor.search(p),
      "download.start": (p) => this.downloadsExecutor.download(p),
      "download.pause": (p) => this.downloadsExecutor.pause(p),
      "download.resume": (p) => this.downloadsExecutor.resume(p),
      "download.cancel": (p) => this.downloadsExecutor.cancel(p),
      "download.erase": (p) => this.downloadsExecutor.erase(p),
      "download.open": (p) => this.downloadsExecutor.open(p),
      // 会话类
      "session.recent": (p) => this.sessionsExecutor.recent(p),
      "session.restore": (p) => this.sessionsExecutor.restore(p),
      // 常访问站点类
      "topsite.list": (p) => this.topSitesExecutor.list(p),
      // 阅读列表类
      "readinglist.list": (p) => this.readingListExecutor.list(p),
      "readinglist.add": (p) => this.readingListExecutor.add(p),
      "readinglist.remove": (p) => this.readingListExecutor.remove(p),
      "readinglist.update": (p) => this.readingListExecutor.update(p),
      // 右键菜单类
      "contextmenu.create": (p) => this.contextMenusExecutor.create(p),
      "contextmenu.remove": (p) => this.contextMenusExecutor.remove(p),
      "contextmenu.remove_all": (p) => this.contextMenusExecutor.removeAll(p),
      "contextmenu.list": (p) => this.contextMenusExecutor.list(p),
      // 定时器类
      "alarm.create": (p) => this.alarmsExecutor.create(p),
      "alarm.list": (p) => this.alarmsExecutor.list(p),
      "alarm.clear": (p) => this.alarmsExecutor.clear(p),
      "alarm.clear_all": (p) => this.alarmsExecutor.clearAll(p),
      // 通知类
      "notification.create": (p) => this.notificationsExecutor.create(p),
      "notification.clear": (p) => this.notificationsExecutor.clear(p),
      "notification.clear_all": (p) => this.notificationsExecutor.clearAll(p),
      "notification.list": (p) => this.notificationsExecutor.getAll(p),
      // 搜索类
      "search.query": (p) => this.searchExecutor.query(p),
      // 空闲状态类
      "idle.query_state": (p) => this.idleExecutor.queryState(p),
      "idle.set_interval": (p) => this.idleExecutor.setInterval(p),
      "idle.get_interval": (p) => this.idleExecutor.getInterval(p),
      // 站点图标类
      "favicon.get_url": (p) => this.faviconExecutor.getUrl(p),
      // 页面导航事件类
      "webnav.get_all_frames": (p) =>
        this.webNavigationExecutor.getAllFrames(p),
      "webnav.get_frame": (p) => this.webNavigationExecutor.getFrame(p),
      // 标签组类
      "tabgroup.list": (p) => this.tabGroupsExecutor.list(p),
      "tabgroup.get": (p) => this.tabGroupsExecutor.get(p),
      "tabgroup.query": (p) => this.tabGroupsExecutor.query(p),
      "tabgroup.update": (p) => this.tabGroupsExecutor.update(p),
      // ===== 以下为高敏感能力，调用前必须向用户确认 =====
      // Cookie 类（高敏感）
      "cookie.get": (p) => this.cookiesExecutor.get(p),
      "cookie.get_all": (p) => this.cookiesExecutor.getAll(p),
      "cookie.set": (p) => this.cookiesExecutor.set(p),
      "cookie.remove": (p) => this.cookiesExecutor.remove(p),
      // 网络请求规则类（高敏感，基于 declarativeNetRequest）
      "netrule.list": (p) => this.webRequestExecutor.listRules(p),
      "netrule.register": (p) => this.webRequestExecutor.registerRule(p),
      "netrule.unregister": (p) => this.webRequestExecutor.unregisterRule(p),
      // 扩展与应用管理类（高敏感，卸载/禁用不可逆）
      "extmgr.list": (p) => this.managementExecutor.list(p),
      "extmgr.get": (p) => this.managementExecutor.get(p),
      "extmgr.launch_app": (p) => this.managementExecutor.launchApp(p),
      "extmgr.set_enabled": (p) => this.managementExecutor.setEnabled(p),
      "extmgr.uninstall": (p) => this.managementExecutor.uninstall(p),
      // 本机消息类（高敏感，需已注册 native host）
      "native.send": (p) => this.nativeMessagingExecutor.send(p),
      // 代理类（高敏感，影响全部网络流量）
      "proxy.get_settings": (p) => this.proxyExecutor.getSettings(p),
      "proxy.set_settings": (p) => this.proxyExecutor.setSettings(p),
      "proxy.clear_settings": (p) => this.proxyExecutor.clearSettings(p),
      // 隐私设置类（高敏感）
      "privacy.get": (p) => this.privacyExecutor.get(p),
      "privacy.set": (p) => this.privacyExecutor.set(p),
      // 浏览数据类（高敏感，remove 不可逆）
      "browsingdata.settings": (p) => this.browsingDataExecutor.settings(p),
      "browsingdata.remove": (p) => this.browsingDataExecutor.remove(p),
      // 内容设置类（高敏感）
      "contentsettings.get": (p) => this.contentSettingsExecutor.get(p),
      "contentsettings.set": (p) => this.contentSettingsExecutor.set(p),
      "contentsettings.clear": (p) => this.contentSettingsExecutor.clear(p),
    };
  }

  /**
   * 返回本扩展支持的能力清单（供 hello 上报给网关，网关透传给前端能力清单展示）。
   * 每个能力与 routes 中的 action 一一对应；平台固定为 "browser"。
   * @returns {Array<{name:string, description:string, parameters:object, platform:string}>}
   */
  getCapabilities() {
    return CAPABILITIES;
  }

  /**
   * 执行一条指令，返回结果信封。
   * @param {object} msg 指令消息
   * @param {object} [ctx] 执行上下文（命令来源网关与登录 Token），供截图上传等能力使用
   * @returns {Promise<object>} 结果信封
   */
  async handle(msg, ctx = {}) {
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

/**
 * 本扩展对外暴露的能力清单（动态上报给网关）。
 * 每一项与 CommandRouter.routes 中的 action 对应，name 即 action 名；
 * 网关/前端据此展示「该插件具有哪些能力」，与 daemon 能力清单格式对齐。
 */
const CAPABILITIES = [
  {
    name: "tab.list",
    description: "列出浏览器当前打开的标签页",
    parameters: {},
    platform: "browser",
  },
  {
    name: "tab.create",
    description: "新建标签页（可指定 URL 与是否新窗口）",
    parameters: { url: "string", new_window: "boolean" },
    platform: "browser",
  },
  {
    name: "tab.close",
    description: "关闭指定标签页",
    parameters: { tab_id: "number" },
    platform: "browser",
  },
  {
    name: "tab.activate",
    description: "切换到指定标签页",
    parameters: { tab_id: "number" },
    platform: "browser",
  },
  {
    name: "page.navigate",
    description: "导航到指定 URL",
    parameters: { url: "string", tab_id: "number" },
    platform: "browser",
  },
  {
    name: "page.reload",
    description: "重新加载当前页面",
    parameters: { tab_id: "number" },
    platform: "browser",
  },
  {
    name: "page.get_info",
    description: "读取页面基础信息（URL/标题/就绪状态等）",
    parameters: {},
    platform: "browser",
  },
  {
    name: "dom.query",
    description: "查询页面元素信息",
    parameters: { selector: "string", all: "boolean" },
    platform: "browser",
  },
  {
    name: "dom.get_text",
    description: "读取元素文本",
    parameters: { selector: "string" },
    platform: "browser",
  },
  {
    name: "dom.click",
    description: "点击页面元素",
    parameters: { selector: "string" },
    platform: "browser",
  },
  {
    name: "dom.type",
    description: "向输入框输入文本",
    parameters: { selector: "string", text: "string" },
    platform: "browser",
  },
  {
    name: "dom.press_key",
    description: "按下键盘按键",
    parameters: { key: "string" },
    platform: "browser",
  },
  {
    name: "script.execute",
    description: "在页面执行任意 JS 脚本（主世界）",
    parameters: { code: "string" },
    platform: "browser",
  },
  {
    name: "script.run",
    description: "运行扩展内已安装的自定义页面脚本",
    parameters: { id: "string", action: "string", args: "object" },
    platform: "browser",
  },
  {
    name: "script.install",
    description: "安装自定义页面脚本（类油猴）",
    parameters: { name: "string", source: "string" },
    platform: "browser",
  },
  {
    name: "script.list",
    description: "列出已安装的自定义页面脚本",
    parameters: {},
    platform: "browser",
  },
  {
    name: "capture.screenshot",
    description: "对页面截图",
    parameters: { full_page: "boolean" },
    platform: "browser",
  },
  {
    name: "debugger.evaluate",
    description: "通过 CDP 求值任意表达式（不受页面 CSP 限制）",
    parameters: { expression: "string" },
    platform: "browser",
  },
  {
    name: "console.get_logs",
    description: "读取页面控制台日志",
    parameters: { limit: "number" },
    platform: "browser",
  },
  {
    name: "network.get_requests",
    description: "采集页面网络请求",
    parameters: { duration_ms: "number", filter: "string" },
    platform: "browser",
  },
  {
    name: "search.query",
    description: "用默认搜索引擎检索",
    parameters: { query: "string" },
    platform: "browser",
  },
  {
    name: "clipboard.write",
    description: "把文本或图片写入系统剪贴板",
    parameters: { text: "string" },
    platform: "browser",
  },
  {
    name: "bookmark.list",
    description: "列出书签",
    parameters: {},
    platform: "browser",
  },
  {
    name: "history.search",
    description: "查询浏览历史",
    parameters: { query: "string" },
    platform: "browser",
  },
  {
    name: "download.list",
    description: "列出下载记录",
    parameters: {},
    platform: "browser",
  },
  {
    name: "download.start",
    description: "发起下载任务",
    parameters: { url: "string" },
    platform: "browser",
  },
  {
    name: "notification.create",
    description: "弹出系统通知",
    parameters: { title: "string", message: "string" },
    platform: "browser",
  },
  {
    name: "alarm.create",
    description: "创建定时器",
    parameters: { name: "string", delay_minutes: "number" },
    platform: "browser",
  },
  {
    name: "session.recent",
    description: "列出最近关闭的标签页/窗口",
    parameters: {},
    platform: "browser",
  },
  {
    name: "cookie.get",
    description: "读取站点 Cookie（高敏感，涉及登录凭证）",
    parameters: { url: "string", name: "string" },
    platform: "browser",
  },
  {
    name: "cookie.set",
    description: "写入/修改 Cookie（高敏感）",
    parameters: { url: "string", name: "string", value: "string" },
    platform: "browser",
  },
  {
    name: "extmgr.list",
    description: "列出已安装扩展（高敏感）",
    parameters: {},
    platform: "browser",
  },
  {
    name: "proxy.get_settings",
    description: "读取浏览器代理配置（高敏感）",
    parameters: {},
    platform: "browser",
  },
  {
    name: "browsingdata.remove",
    description: "清除浏览数据（高敏感，不可逆）",
    parameters: { data_types: "array" },
    platform: "browser",
  },
];

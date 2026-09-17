# -*- coding: utf-8 -*-
"""浏览器扩展工具 - 通过用户本地浏览器扩展操作用户真实浏览器中的网页。

与 jarvis-browser(jb) 的区别：jb 在服务端用 Playwright 启动独立浏览器，
本工具驱动的是**用户自己浏览器**中已登录的真实标签页。

依赖用户浏览器安装 Jarvis Browser Bridge 扩展并连接到网关。
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

import jarvis.jarvis_utils.globals as jglobals

logger = logging.getLogger(__name__)


class BrowserExtTool:
    """浏览器扩展工具，操作用户真实浏览器。

    支持的操作（action）：
    1. **list_sessions**: 列出当前在线的浏览器扩展会话
    2. **list_tabs**: 列出指定会话的标签页
    3. **navigate**: 导航到指定 URL
    4. **get_text**: 读取元素文本
    5. **click**: 点击元素
    6. **type**: 向输入框输入文本
    7. **screenshot**: 截图
    8. **activate_tab**: 激活（切换到）指定标签页
    9. **close_tab**: 关闭指定标签页
    10. **new_tab**: 新建标签页（默认在新窗口打开）
    11. **reload**: 重新加载标签页
    12. **back**: 页面前进后退中的「后退」
    13. **forward**: 页面前进后退中的「前进」
    14. **query**: 查询元素信息（tag/text/value/id/class）
    15. **get_html**: 读取元素 innerHTML
    16. **hover**: 悬停元素
    17. **select**: 选择下拉框选项
    18. **wait_for**: 等待元素出现/消失
    19. **press_key**: 按下键盘按键（可选聚焦指定元素）
    20. **scroll**: 滚动页面或滚动到指定元素
    21. **execute_script**: 在页面中执行任意 JS 代码（高危）
    22. **upload_file**: 上传本地文件到 file input（需 debugger 权限）
    23. **script_list**: 列出扩展里已安装的页面脚本（类油猴）
    24. **script_get**: 读取某个已安装脚本的源码（含 action 清单）
    25. **script_run**: 在目标页主世界执行已安装脚本的某个 action
    26. **script_install**: 安装（或更新）页面脚本（类油猴），需提供名称与源码
    27. **script_install_from_url**: 从 URL 下载并安装页面脚本（源码不经对话传输）
    28. **script_uninstall**: 卸载页面脚本（不可逆）
    29. **script_export**: 导出页面脚本源码为可分享文本
    30. **script_set_enabled**: 启用/停用页面脚本
    31. **script_save**: 把扩展里已安装的脚本保存到网关数据目录（只回传路径与大小，不回传源码）
    32. **script_load_from_file**: 从网关数据目录读取脚本并安装到扩展（只回传元数据，不回传源码）
    32. **clipboard_write**: 把文本或 base64 二进制写入前端页面剪贴板
    33. **clipboard_write_from_url**: 读取网关静态文件并写入前端页面剪贴板
    34. **bookmark_list**: 列出书签（整棵树或指定文件夹）
    35. **bookmark_search**: 按标题/URL 关键字搜索书签
    36. **bookmark_create**: 新增书签
    37. **bookmark_remove**: 删除单个书签（不可逆）
    38. **bookmark_remove_tree**: 删除书签文件夹（不可逆）
    39. **history_search**: 按关键字/时间范围查询历史记录
    40. **history_recent**: 取最近若干条历史记录
    41. **history_remove**: 按 URL 删除历史记录（不可逆）
    42. **history_remove_range**: 按时间范围删除历史记录（不可逆）
    43. **download_list**: 列出下载记录
    44. **download_search**: 按文件名/URL 搜索下载记录
    45. **download_start**: 新建下载任务
    46. **download_pause**: 暂停下载
    47. **download_resume**: 继续下载
    48. **download_cancel**: 取消下载
    49. **download_erase**: 从下载列表移除记录（不可逆）
    50. **download_open**: 用系统默认程序打开已下载文件
    51. **session_recent**: 列出最近关闭的标签页/窗口会话
    52. **session_restore**: 恢复指定会话
    53. **topsite_list**: 列出最常访问的站点
    54. **readinglist_list**: 列出阅读列表
    55. **readinglist_add**: 添加阅读列表条目
    56. **readinglist_remove**: 移除阅读列表条目
    57. **readinglist_update**: 更新阅读列表条目（已读状态/标题）
    58. **contextmenu_create**: 创建扩展右键菜单
    59. **contextmenu_remove**: 移除右键菜单
    60. **contextmenu_remove_all**: 移除全部扩展右键菜单
    61. **contextmenu_list**: 列出扩展右键菜单
    62. **alarm_create**: 创建定时器
    63. **alarm_list**: 列出定时器
    64. **alarm_clear**: 清除定时器
    65. **alarm_clear_all**: 清除全部定时器
    66. **notification_create**: 弹出系统通知
    67. **notification_clear**: 关闭指定通知
    68. **notification_clear_all**: 关闭全部通知
    69. **notification_list**: 列出当前通知
    70. **search_query**: 用浏览器默认搜索引擎检索
    71. **idle_query_state**: 查询浏览器空闲状态
    72. **idle_set_interval**: 设置空闲检测间隔
    73. **idle_get_interval**: 读取空闲检测间隔
    74. **favicon_get_url**: 获取站点图标 URL
    75. **webnav_get_all_frames**: 列出页面全部框架
    76. **webnav_get_frame**: 获取指定框架信息
    77. **tabgroup_list**: 列出标签组
    78. **tabgroup_get**: 获取标签组详情
    79. **tabgroup_query**: 按标题/颜色/窗口查询标签组
    80. **tabgroup_update**: 更新标签组（标题/颜色/折叠）
    81. **cookie_get**（高敏感）: 读取单个 Cookie
    82. **cookie_get_all**（高敏感）: 读取站点 Cookie 列表
    83. **cookie_set**（高敏感）: 写入/修改 Cookie
    84. **cookie_remove**（高敏感）: 删除 Cookie
    85. **netrule_list**（高敏感）: 列出网络请求规则
    86. **netrule_register**（高敏感）: 注册网络请求规则（可改写/阻断请求）
    87. **netrule_unregister**（高敏感）: 注销网络请求规则
    88. **extmgr_list**（高敏感）: 列出已安装扩展与应用
    89. **extmgr_get**（高敏感）: 获取扩展详情
    90. **extmgr_launch_app**（高敏感）: 启动已安装应用
    91. **extmgr_set_enabled**（高敏感）: 启用/禁用扩展
    92. **extmgr_uninstall**（高敏感，不可逆）: 卸载扩展
    93. **native_send**（高敏感）: 向本机应用发送消息（需已注册 native host）
    94. **proxy_get_settings**（高敏感）: 读取浏览器代理配置
    95. **proxy_set_settings**（高敏感）: 设置浏览器代理（影响全部网络流量）
    96. **proxy_clear_settings**（高敏感）: 清除代理配置
    97. **privacy_get**（高敏感）: 读取隐私设置
    98. **privacy_set**（高敏感）: 修改隐私设置
    99. **browsingdata_settings**（高敏感）: 查询可清理的浏览数据类型
    100. **browsingdata_remove**（高敏感，不可逆）: 清除浏览数据（历史/Cookie/缓存/密码等）
    101. **contentsettings_get**（高敏感）: 读取站点内容设置
    102. **contentsettings_set**（高敏感）: 修改站点内容设置
    103. **contentsettings_clear**（高敏感）: 清除站点内容设置

    典型流程：先 list_sessions 拿到 session_id，再 list_tabs 拿到 tab_id，
    然后执行 navigate/get_text/click/type/screenshot 等操作。
    若目标站点已安装对应脚本，应优先 script_list/script_get/script_run 复用其能力。

    **重要提示**：
    - 每次调用只能执行一种操作
    - 操作的是用户真实浏览器，请谨慎执行可能造成不可逆后果的动作
    """

    name = "browser_ext"

    @staticmethod
    def check() -> bool:
        """检查工具是否可用，仅当 Gateway 存在时启用（通过 agent_id 是否设置判断）。"""
        return jglobals.agent_id is not None

    description = """操作用户本地真实浏览器中的网页（通过用户安装的浏览器扩展）。
与 read_webpage 等工具不同：本工具操作的是**用户自己浏览器**里已登录的标签页，可复用登录态与 Cookie。
每次调用只能执行一个 action：
- list_sessions: 列出当前在线的浏览器会话（返回 session_id 列表）。**应先调用此操作获取 session_id**
- list_tabs: 列出指定会话的标签页（返回 tab_id/url/title）。需 session_id
- navigate: 导航到指定 URL。需 session_id、url；可选 tab_id（不传则新建页面，默认在新窗口打开，可用 new_window=false 改为新建标签页）
- get_text: 读取元素文本。需 session_id、selector；可选 tab_id
- click: 点击元素。需 session_id、selector；可选 tab_id
- type: 向输入框输入文本。需 session_id、selector、text；可选 tab_id
- screenshot: 截图。需 session_id；可选 tab_id
- activate_tab: 激活（切换到）指定标签页。需 session_id、tab_id
- close_tab: 关闭指定标签页。需 session_id、tab_id
- new_tab: 新建标签页。需 session_id；可选 url（不传则 about:blank）、new_window（默认 true，在新窗口打开并聚焦，保证页面在前台正常渲染；false 则在当前窗口新建标签页）
- reload: 重新加载标签页。需 session_id；可选 tab_id（不传则当前活动页）
- back: 后退。需 session_id；可选 tab_id（不传则当前活动页）
- forward: 前进。需 session_id；可选 tab_id（不传则当前活动页）
- query: 查询元素信息。需 session_id、selector；可选 tab_id、all（true 返回全部匹配）
- get_html: 读取元素 innerHTML。需 session_id、selector；可选 tab_id
- hover: 悬停元素。需 session_id、selector；可选 tab_id
- select: 选择下拉框选项。需 session_id、selector、value；可选 tab_id
- wait_for: 等待元素出现/消失。需 session_id、selector；可选 tab_id、state（visible/hidden/attached，默认 visible）、timeout_ms（默认 15000）
- press_key: 按下键盘按键。需 session_id、key（如 Enter/Escape/Tab/ArrowDown）；可选 tab_id、selector（不传则作用于当前焦点元素）
- scroll: 滚动页面。需 session_id；可选 tab_id、selector（滚动到该元素）、x/y（像素偏移，正数向右/向下）、behavior（auto/smooth）
- execute_script: 在页面中执行任意 JS 代码（高危）。需 session_id、code；可选 tab_id、world（ISOLATED/MAIN，默认 MAIN）。
  code 中可直接写 return 返回结果（如 "return document.title"），也支持 await；返回值需可 JSON 序列化。
  默认在 MAIN 世界执行以复用页面自身的 JS 环境与登录态；部分站点的 CSP 会限制 ISOLATED 世界的 eval，故不推荐改回 ISOLATED。
- upload_file: 上传本地文件到 file input。需 session_id、selector、file_path（本地绝对路径）；可选 tab_id。依赖 chrome.debugger，扩展需具备 debugger 权限
- get_computed_style: 读取元素的计算样式（相当于 F12 Computed 面板）。需 session_id、selector；可选 tab_id、props（CSS 属性名数组，如 ["display","color"]，不传则返回常用属性集合）
- get_page_info: 读取页面基础信息（相当于 F12 概览）。需 session_id；可选 tab_id。返回 url/title/ready_state/viewport/scroll/document
- get_console_logs: 读取页面 console 日志（相当于 F12 Console 面板）。需 session_id；可选 tab_id、limit（默认 100）、clear（读取后是否清空缓存）。
  首次调用会安装 hook，之后需页面产生新的日志才会被采集
- evaluate: 通过 CDP 在页面中求值任意表达式（不受页面 CSP 限制，相当于 F12 Console 直接敲表达式）。需 session_id、expression；可选 tab_id、await_promise（默认 true）
- send_cdp_command: 透传任意 CDP 命令（相当于直接使用 DevTools Protocol）。需 session_id、method（CDP 方法名）；可选 tab_id、cdp_params（方法参数对象）。
  用于 Runtime/DOM 域之外的场景，如 method="Page.addScriptToEvaluateOnNewDocument" 在文档创建前注入脚本
- get_network_requests: 采集页面网络请求（相当于 F12 Network 面板）。需 session_id；可选 tab_id、duration_ms（采集时长，默认 3000）、limit（默认 100）、filter（URL 子串过滤）。
  注意：会阻塞 duration_ms 毫秒进行采集，建议先触发页面动作再调用
- script_list: 列出扩展里已安装的页面脚本（类油猴脚本）的元数据（id/name/description/match/enabled/version）。需 session_id。
  **接到浏览器任务时应先调用它盘点有无现成脚本可复用**——脚本在页面主世界执行，能力远强于裸 DOM 操作
- script_get: 读取某个已安装脚本的完整信息（含 source 源码，据此得知它导出哪些 action、参数与行为）。需 session_id、script_id
- script_run: 在目标页主世界执行已安装脚本的某个 action。需 session_id、script_id、script_action；可选 script_args（传给该 action 的参数对象）、tab_id（默认当前活动页）。
  脚本须 enabled 且目标页 URL 命中其 match；写操作类 action 会真实改动数据，调用前先向用户说明
- script_install: 安装（或更新）页面脚本。需 session_id、script_name、script_source；可选 script_description、script_match（URL 匹配模式数组）、script_version。
  源码需导出 actions 映射（可写 globalThis.__JARVIS_SCRIPT__ 或 module.exports）；安装后默认启用
- script_install_from_url: 从 URL 下载并安装页面脚本。需 session_id、script_url；可选 script_name、script_description、script_match、script_version。
  仅支持 http/https 且拒绝内网/回环地址（防 SSRF）；源码由扩展后台下载，**不进入对话上下文**，适合脚本体量较大的场景
- script_uninstall: 卸载页面脚本（**不可逆**）。需 session_id、script_id
- script_export: 导出页面脚本源码为可分享文本。需 session_id、script_id。用于备份或迁移脚本
- script_set_enabled: 启用/停用页面脚本。需 session_id、script_id、script_enabled（布尔）。停用后 script_run 会返回 SCRIPT_DISABLED
- script_save: 把扩展里已安装的脚本保存到网关数据目录（`{数据目录}/browser_scripts/`）。需 session_id、script_id；可选 script_name（保存用的文件名，不传则用脚本自身名称）。
  **只返回保存路径与字节数，不回传脚本原文**。适合把脚本备份到网关，或为「从文件安装」做中转，避免大段源码占用上下文
- script_load_from_file: 从网关数据目录读取脚本并安装到扩展。需 session_id、script_name（文件名/脚本名）；可选 script_description、script_match、script_version。
  **只返回安装结果元数据，不回传脚本原文**。与 script_save 配对使用，可在不传输源码的情况下迁移/部署脚本
- clipboard_write: 把文本或 base64 二进制写入**前端页面**的系统剪贴板。需 session_id；
  文本用 clipboard_text，二进制用 clipboard_base64（配合 clipboard_mime，默认 image/png）；
  可选 clipboard_as（text/blob，不传时有 clipboard_text 则用 text）、tab_id。
  要求目标页真正获得焦点，否则报 CLIPBOARD_WRITE_FAILED
- clipboard_write_from_url: 读取文件内容并写入前端页面剪贴板。需 session_id、clipboard_url；可选 clipboard_as、clipboard_mime、tab_id。
  推荐传完整绝对 URL；相对路径仅支持 /uploads/ 前缀（用已连接网关补全）
- bookmark_list: 列出书签。需 session_id；可选 parent_id（指定文件夹 ID，不传则返回整棵书签树）
- bookmark_search: 按标题或 URL 关键字搜索书签。需 session_id、bookmark_query；可选 max_results
- bookmark_create: 新增书签。需 session_id、url；可选 title、parent_id（不传则放入「其他书签」）
- bookmark_remove: 删除单个书签（**不可逆**）。需 session_id、bookmark_id
- bookmark_remove_tree: 删除书签文件夹及其全部子节点（**不可逆**）。需 session_id、bookmark_id
- history_search: 查询历史记录。需 session_id；可选 history_query（关键字）、start_time/end_time（毫秒时间戳）、max_results（默认 100）
- history_recent: 取最近若干条历史记录（按访问时间倒序）。需 session_id；可选 max_results（默认 50）
- history_remove: 删除指定 URL 的全部历史记录（**不可逆**）。需 session_id、history_url
- history_remove_range: 删除时间区间内的历史记录（**不可逆**）。需 session_id；可选 start_time/end_time（毫秒时间戳）。
  **不传时间参数会清空全部历史记录**，调用前务必向用户确认
- download_list: 列出下载记录。需 session_id；可选 download_query（关键字）、max_results（默认 50）
- download_search: 按文件名/URL 搜索下载记录。需 session_id、download_query；可选 max_results
- download_start: 新建下载任务。需 session_id、url；可选 filename、save_as（默认 true）
- download_pause: 暂停下载。需 session_id、download_id
- download_resume: 继续下载。需 session_id、download_id
- download_cancel: 取消下载。需 session_id、download_id
- download_erase: 从下载列表移除记录（**不可逆**）。需 session_id、download_id；可选 delete_file（默认 false，true 会同时删除磁盘文件）
- download_open: 用系统默认程序打开已下载文件。需 session_id、download_id
- session_recent: 列出最近关闭的标签页/窗口会话。需 session_id；可选 max_results（默认 25）
- session_restore: 恢复指定会话。需 session_id、session_key（由 session_recent 获取）
- topsite_list: 列出最常访问的站点。需 session_id
- readinglist_list: 列出阅读列表。需 session_id
- readinglist_add: 添加阅读列表条目。需 session_id、url；可选 title、has_been_read
- readinglist_remove: 移除阅读列表条目。需 session_id、url
- readinglist_update: 更新阅读列表条目。需 session_id、url；可选 has_been_read、title
- contextmenu_create: 创建扩展右键菜单。需 session_id、menu_id、title；可选 contexts、url_patterns
- contextmenu_remove: 移除右键菜单。需 session_id、menu_id
- contextmenu_remove_all: 移除全部扩展右键菜单。需 session_id
- contextmenu_list: 列出扩展右键菜单。需 session_id
- alarm_create: 创建定时器。需 session_id、alarm_name；可选 delay_minutes、period_minutes
- alarm_list: 列出定时器。需 session_id
- alarm_clear: 清除定时器。需 session_id、alarm_name
- alarm_clear_all: 清除全部定时器。需 session_id
- notification_create: 弹出系统通知。需 session_id、title；可选 notification_id、message、icon_url
- notification_clear: 关闭指定通知。需 session_id、notification_id
- notification_clear_all: 关闭全部通知。需 session_id
- notification_list: 列出当前通知。需 session_id
- search_query: 用浏览器默认搜索引擎检索。需 session_id、search_query；可选 tab_id、disposition
- idle_query_state: 查询浏览器空闲状态。需 session_id；可选 detection_interval_seconds
- idle_set_interval: 设置空闲检测间隔。需 session_id、detection_interval_seconds
- idle_get_interval: 读取空闲检测间隔。需 session_id
- favicon_get_url: 获取站点图标 URL。需 session_id、page_url；可选 size
- webnav_get_all_frames: 列出页面全部框架。需 session_id、tab_id
- webnav_get_frame: 获取指定框架信息。需 session_id、tab_id、frame_id
- tabgroup_list: 列出标签组。需 session_id
- tabgroup_get: 获取标签组详情。需 session_id、group_id
- tabgroup_query: 按标题/颜色/窗口查询标签组。需 session_id；可选 group_title、color、window_id
- tabgroup_update: 更新标签组。需 session_id、group_id；可选 group_title、color、collapsed

**以下为高敏感操作，会真实改动用户浏览器配置或数据，调用前必须向用户确认：**
- cookie_get: 读取单个 Cookie（**高敏感**，涉及登录凭证）。需 session_id、url、cookie_name
- cookie_get_all: 读取站点 Cookie 列表（**高敏感**）。需 session_id；可选 url、domain
- cookie_set: 写入/修改 Cookie（**高敏感**）。需 session_id、url、cookie_name、value；可选 domain、path、secure、http_only、same_site、expiration_date
- cookie_remove: 删除 Cookie（**高敏感**）。需 session_id、url、cookie_name
- netrule_list: 列出网络请求规则（**高敏感**）。需 session_id
- netrule_register: 注册网络请求规则（**高敏感**，可阻断/重定向请求）。需 session_id、rule_id、url_filter；可选 action_type（block/redirect/allow，默认 block）、redirect_url、priority
- netrule_unregister: 注销网络请求规则（**高敏感**）。需 session_id、rule_id
- extmgr_list: 列出已安装扩展与应用（**高敏感**）。需 session_id
- extmgr_get: 获取扩展详情（**高敏感**）。需 session_id、extension_id
- extmgr_launch_app: 启动已安装应用（**高敏感**）。需 session_id、extension_id
- extmgr_set_enabled: 启用/禁用扩展（**高敏感**）。需 session_id、extension_id、enabled
- extmgr_uninstall: 卸载扩展（**高敏感，不可逆**）。需 session_id、extension_id
- native_send: 向本机应用发送消息（**高敏感**，需已注册 native host）。需 session_id、native_host、message
- proxy_get_settings: 读取浏览器代理配置（**高敏感**）。需 session_id
- proxy_set_settings: 设置浏览器代理（**高敏感**，影响全部网络流量）。需 session_id、proxy_mode（direct/auto_detect/pac_script/system/fixed_servers）；pac_script 需 pac_url，fixed_servers 需 proxy_rules
- proxy_clear_settings: 清除代理配置（**高敏感**）。需 session_id
- privacy_get: 读取隐私设置（**高敏感**）。需 session_id、privacy_area（network/services/websites）、privacy_name
- privacy_set: 修改隐私设置（**高敏感**）。需 session_id、privacy_area、privacy_name、privacy_value
- browsingdata_settings: 查询可清理的浏览数据类型（**高敏感**）。需 session_id
- browsingdata_remove: 清除浏览数据（**高敏感，不可逆**）。需 session_id、data_types（数组，如 ["cache","cookies","history","downloads","formData","passwords"]）；可选 since（毫秒时间戳，不传清除全部）
- contentsettings_get: 读取站点内容设置（**高敏感**）。需 session_id、content_type；可选 primary_url、secondary_url
- contentsettings_set: 修改站点内容设置（**高敏感**）。需 session_id、content_type、content_setting；可选 primary_pattern、secondary_pattern
- contentsettings_clear: 清除站点内容设置（**高敏感**）。需 session_id、content_type
若用户未安装扩展或扩展未连接，list_sessions 会返回空列表。"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list_sessions",
                    "list_tabs",
                    "navigate",
                    "get_text",
                    "click",
                    "type",
                    "screenshot",
                    "activate_tab",
                    "close_tab",
                    "new_tab",
                    "reload",
                    "back",
                    "forward",
                    "query",
                    "get_html",
                    "hover",
                    "select",
                    "wait_for",
                    "press_key",
                    "scroll",
                    "execute_script",
                    "upload_file",
                    "get_computed_style",
                    "get_page_info",
                    "get_console_logs",
                    "evaluate",
                    "send_cdp_command",
                    "get_network_requests",
                    "script_list",
                    "script_get",
                    "script_run",
                    "script_install",
                    "script_install_from_url",
                    "script_uninstall",
                    "script_export",
                    "script_set_enabled",
                    "script_save",
                    "script_load_from_file",
                    "clipboard_write",
                    "clipboard_write_from_url",
                    "bookmark_list",
                    "bookmark_search",
                    "bookmark_create",
                    "bookmark_remove",
                    "bookmark_remove_tree",
                    "history_search",
                    "history_recent",
                    "history_remove",
                    "history_remove_range",
                    "download_list",
                    "download_search",
                    "download_start",
                    "download_pause",
                    "download_resume",
                    "download_cancel",
                    "download_erase",
                    "download_open",
                    "session_recent",
                    "session_restore",
                    "topsite_list",
                    "readinglist_list",
                    "readinglist_add",
                    "readinglist_remove",
                    "readinglist_update",
                    "contextmenu_create",
                    "contextmenu_remove",
                    "contextmenu_remove_all",
                    "contextmenu_list",
                    "alarm_create",
                    "alarm_list",
                    "alarm_clear",
                    "alarm_clear_all",
                    "notification_create",
                    "notification_clear",
                    "notification_clear_all",
                    "notification_list",
                    "search_query",
                    "idle_query_state",
                    "idle_set_interval",
                    "idle_get_interval",
                    "favicon_get_url",
                    "webnav_get_all_frames",
                    "webnav_get_frame",
                    "tabgroup_list",
                    "tabgroup_get",
                    "tabgroup_query",
                    "tabgroup_update",
                    "cookie_get",
                    "cookie_get_all",
                    "cookie_set",
                    "cookie_remove",
                    "netrule_list",
                    "netrule_register",
                    "netrule_unregister",
                    "extmgr_list",
                    "extmgr_get",
                    "extmgr_launch_app",
                    "extmgr_set_enabled",
                    "extmgr_uninstall",
                    "native_send",
                    "proxy_get_settings",
                    "proxy_set_settings",
                    "proxy_clear_settings",
                    "privacy_get",
                    "privacy_set",
                    "browsingdata_settings",
                    "browsingdata_remove",
                    "contentsettings_get",
                    "contentsettings_set",
                    "contentsettings_clear",
                ],
                "description": "要执行的操作类型，每次只能选一个",
            },
            "session_id": {
                "type": "string",
                "description": "浏览器扩展会话 ID（由 list_sessions 获取；除 list_sessions 外均必填）",
            },
            "tab_id": {
                "type": "integer",
                "description": "目标标签页 ID（由 list_tabs 获取；navigate 不传则新建标签页）",
            },
            "url": {
                "type": "string",
                "description": "要导航到的 URL（navigate 操作必填）",
            },
            "selector": {
                "type": "string",
                "description": "CSS 选择器（get_text/click/type 操作必填）",
            },
            "text": {
                "type": "string",
                "description": "要输入的文本（type 操作必填）",
            },
            "value": {
                "type": "string",
                "description": "下拉框选项的值（select 操作必填）",
            },
            "state": {
                "type": "string",
                "enum": ["visible", "hidden", "attached"],
                "description": "等待的目标状态（wait_for 可选，默认 visible）",
            },
            "all": {
                "type": "boolean",
                "description": "是否返回全部匹配元素（query 可选，默认 false 只返回首个）",
            },
            "key": {
                "type": "string",
                "description": "要按下的键，如 Enter/Escape/Tab/ArrowDown（press_key 必填）",
            },
            "x": {
                "type": "integer",
                "description": "水平滚动像素（scroll 可选，正数向右）",
            },
            "y": {
                "type": "integer",
                "description": "垂直滚动像素（scroll 可选，正数向下）",
            },
            "behavior": {
                "type": "string",
                "enum": ["auto", "smooth"],
                "description": "滚动行为（scroll 可选，默认 auto）",
            },
            "code": {
                "type": "string",
                "description": "要执行的 JavaScript 代码（execute_script 必填，高危）",
            },
            "world": {
                "type": "string",
                "enum": ["ISOLATED", "MAIN"],
                "description": "脚本执行环境（execute_script 可选，默认 ISOLATED）",
            },
            "file_path": {
                "type": "string",
                "description": "要上传的本地文件绝对路径（upload_file 必填）",
            },
            "full_page": {
                "type": "boolean",
                "description": "是否整页截图（screenshot 可选，默认 false 仅当前视口）",
            },
            "props": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要读取的 CSS 属性名数组，kebab-case（get_computed_style 可选，不传则返回常用属性集合）",
            },
            "expression": {
                "type": "string",
                "description": "要通过 CDP 求值的 JavaScript 表达式（evaluate 必填）",
            },
            "await_promise": {
                "type": "boolean",
                "description": "是否等待 Promise 结果（evaluate 可选，默认 true）",
            },
            "method": {
                "type": "string",
                "description": "CDP 方法名，如 Page.addScriptToEvaluateOnNewDocument（send_cdp_command 必填）",
            },
            "cdp_params": {
                "type": "object",
                "description": "CDP 方法参数对象（send_cdp_command 可选）",
            },
            "limit": {
                "type": "integer",
                "description": "最多返回多少条（get_console_logs/get_network_requests 可选，默认 100）",
            },
            "clear": {
                "type": "boolean",
                "description": "读取后是否清空缓存（get_console_logs 可选，默认 false）",
            },
            "duration_ms": {
                "type": "integer",
                "description": "网络请求采集时长毫秒（get_network_requests 可选，默认 3000）",
            },
            "filter": {
                "type": "string",
                "description": "按 URL 子串过滤请求（get_network_requests 可选）",
            },
            "new_window": {
                "type": "boolean",
                "description": "是否在新窗口打开（new_tab 可选，默认 true）。"
                "新窗口会置于前台并聚焦，可保证页面正常渲染与重绘；"
                "设为 false 则在当前窗口新建标签页",
            },
            "script_id": {
                "type": "string",
                "description": "已安装脚本的 ID（由 script_list 获取，形如 s-xxxxxxxx；"
                "script_get/script_run/script_uninstall/script_export/script_set_enabled/script_save 必填）",
            },
            "script_action": {
                "type": "string",
                "description": "要执行的脚本内 action 名（script_run 必填；取自 script_get 返回的源码）",
            },
            "script_args": {
                "type": "object",
                "description": "传给脚本 action 的参数对象（script_run 可选，默认空对象）",
            },
            "script_name": {
                "type": "string",
                "description": "脚本名称。script_install 必填（安装后的脚本名）；"
                "script_save 可选（保存到网关的文件名，不传则用脚本自身名称）；"
                "script_load_from_file 必填（网关目录中的文件名/脚本名）",
            },
            "script_source": {
                "type": "string",
                "description": "脚本源码（script_install 必填；需导出 actions 映射，"
                "可写 globalThis.__JARVIS_SCRIPT__ 或 module.exports）",
            },
            "script_url": {
                "type": "string",
                "description": "脚本下载 URL（script_install_from_url 必填）。"
                "仅支持 http/https，且拒绝内网/回环地址（防 SSRF）；"
                "源码由扩展后台下载，不进入对话上下文",
            },
            "script_description": {
                "type": "string",
                "description": "脚本描述（script_install/script_install_from_url/script_load_from_file 可选）",
            },
            "script_match": {
                "type": "array",
                "items": {"type": "string"},
                "description": "脚本适用的 URL 匹配模式数组（script_install/script_install_from_url/script_load_from_file 可选）",
            },
            "script_version": {
                "type": "string",
                "description": "脚本版本号（script_install/script_install_from_url/script_load_from_file 可选）",
            },
            "script_enabled": {
                "type": "boolean",
                "description": "是否启用脚本（script_set_enabled 必填）",
            },
            "clipboard_text": {
                "type": "string",
                "description": "要写入剪贴板的文本（clipboard_write 在 as='text' 时必填）",
            },
            "clipboard_base64": {
                "type": "string",
                "description": "要写入剪贴板的二进制内容（base64，clipboard_write 在 as='blob' 时必填）",
            },
            "clipboard_mime": {
                "type": "string",
                "description": "MIME 类型（clipboard_write 可选，as='blob' 时默认 image/png）",
            },
            "clipboard_as": {
                "type": "string",
                "enum": ["text", "blob"],
                "description": "写入模式（clipboard_write 可选；不传时有 clipboard_text 则用 text，否则 blob）",
            },
            "clipboard_url": {
                "type": "string",
                "description": "要读取并写入剪贴板的文件地址（clipboard_write_from_url 必填）；"
                "推荐传完整绝对 URL，相对路径仅支持 /uploads/ 前缀",
            },
            "bookmark_query": {
                "type": "string",
                "description": "书签搜索关键字，匹配标题或 URL（bookmark_search 必填）",
            },
            "bookmark_id": {
                "type": "string",
                "description": "书签节点 ID（bookmark_remove/bookmark_remove_tree 必填）",
            },
            "parent_id": {
                "type": "string",
                "description": "书签文件夹 ID（bookmark_list 可选，不传返回整棵树；bookmark_create 可选，不传放入「其他书签」）",
            },
            "history_query": {
                "type": "string",
                "description": "历史记录搜索关键字（history_search 可选，不传则返回时间范围内全部）",
            },
            "history_url": {
                "type": "string",
                "description": "要删除历史记录的 URL（history_remove 必填）",
            },
            "start_time": {
                "type": "integer",
                "description": "起始时间，毫秒时间戳（history_search/history_remove_range 可选，不传则为 0）",
            },
            "end_time": {
                "type": "integer",
                "description": "结束时间，毫秒时间戳（history_search/history_remove_range 可选，不传则为当前时间）",
            },
            "max_results": {
                "type": "integer",
                "description": "最多返回多少条（bookmark_search/history_search/history_recent 可选）",
            },
            "download_query": {
                "type": "string",
                "description": "下载记录搜索关键字，匹配文件名或 URL（download_search 必填；download_list 可选）",
            },
            "download_id": {
                "type": "integer",
                "description": "下载项 ID（download_pause/download_resume/download_cancel/download_erase/download_open 必填）",
            },
            "filename": {
                "type": "string",
                "description": "保存的文件名（download_start 可选）",
            },
            "save_as": {
                "type": "boolean",
                "description": "是否弹出另存为对话框（download_start 可选，默认 true）",
            },
            "delete_file": {
                "type": "boolean",
                "description": "是否同时删除磁盘文件（download_erase 可选，默认 false）",
            },
            "session_key": {
                "type": "string",
                "description": "会话标识（session_restore 必填，由 session_recent 返回）",
            },
            "has_been_read": {
                "type": "boolean",
                "description": "是否已读（readinglist_add/readinglist_update 可选）",
            },
            "menu_id": {
                "type": "string",
                "description": "右键菜单 ID（contextmenu_create/contextmenu_remove 必填）",
            },
            "contexts": {
                "type": "array",
                "items": {"type": "string"},
                "description": '菜单显示上下文，如 ["page","selection"]（contextmenu_create 可选，默认 ["page"]）',
            },
            "url_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "菜单显示匹配的 URL 模式（contextmenu_create 可选）",
            },
            "alarm_name": {
                "type": "string",
                "description": "定时器名称（alarm_create/alarm_clear 必填）",
            },
            "delay_minutes": {
                "type": "number",
                "description": "首次触发延迟分钟数（alarm_create 可选）",
            },
            "period_minutes": {
                "type": "number",
                "description": "重复周期分钟数（alarm_create 可选，不传则只触发一次）",
            },
            "notification_id": {
                "type": "string",
                "description": "通知 ID（notification_create 可选；notification_clear 必填）",
            },
            "message": {
                "type": "string",
                "description": "通知正文（notification_create 可选）或发给本机应用的消息（native_send 必填）",
            },
            "icon_url": {
                "type": "string",
                "description": "通知图标 URL（notification_create 可选）",
            },
            "search_query": {
                "type": "string",
                "description": "搜索关键词（search_query 必填）",
            },
            "disposition": {
                "type": "string",
                "enum": ["CURRENT_TAB", "NEW_TAB", "NEW_WINDOW"],
                "description": "搜索结果打开方式（search_query 可选，默认 CURRENT_TAB）",
            },
            "detection_interval_seconds": {
                "type": "integer",
                "description": "空闲检测间隔秒数（idle_query_state/idle_set_interval 可选，最小 15）",
            },
            "page_url": {
                "type": "string",
                "description": "页面 URL（favicon_get_url 必填）",
            },
            "size": {
                "type": "integer",
                "description": "图标尺寸像素（favicon_get_url 可选，默认 32）",
            },
            "frame_id": {
                "type": "integer",
                "description": "框架 ID（webnav_get_frame 必填，由 webnav_get_all_frames 获取）",
            },
            "group_id": {
                "type": "integer",
                "description": "标签组 ID（tabgroup_get/tabgroup_update 必填）",
            },
            "group_title": {
                "type": "string",
                "description": "标签组标题（tabgroup_query 可选；tabgroup_update 可选，用于重命名）",
            },
            "color": {
                "type": "string",
                "description": "标签组颜色，如 blue/red/green（tabgroup_query/tabgroup_update 可选）",
            },
            "collapsed": {
                "type": "boolean",
                "description": "标签组是否折叠（tabgroup_update 可选）",
            },
            "window_id": {
                "type": "integer",
                "description": "窗口 ID（tabgroup_query 可选）",
            },
            "cookie_name": {
                "type": "string",
                "description": "Cookie 名（cookie_get/cookie_set/cookie_remove 必填）",
            },
            "domain": {
                "type": "string",
                "description": "Cookie 域（cookie_get_all 可选；cookie_set 可选）",
            },
            "path": {
                "type": "string",
                "description": "Cookie 路径（cookie_set 可选）",
            },
            "secure": {
                "type": "boolean",
                "description": "Cookie 是否仅 HTTPS 传输（cookie_set 可选）",
            },
            "http_only": {
                "type": "boolean",
                "description": "Cookie 是否禁止 JS 访问（cookie_set 可选）",
            },
            "same_site": {
                "type": "string",
                "enum": ["no_restriction", "lax", "strict", "unspecified"],
                "description": "Cookie SameSite 策略（cookie_set 可选）",
            },
            "expiration_date": {
                "type": "number",
                "description": "Cookie 过期时间，秒级时间戳（cookie_set 可选，不传为会话 Cookie）",
            },
            "rule_id": {
                "type": "integer",
                "description": "网络请求规则 ID（netrule_register/netrule_unregister 必填）",
            },
            "url_filter": {
                "type": "string",
                "description": "规则匹配的 URL 过滤串（netrule_register 必填）",
            },
            "action_type": {
                "type": "string",
                "enum": ["block", "redirect", "allow"],
                "description": "规则动作（netrule_register 可选，默认 block）",
            },
            "redirect_url": {
                "type": "string",
                "description": "重定向目标 URL（netrule_register 在 action_type=redirect 时必填）",
            },
            "priority": {
                "type": "integer",
                "description": "规则优先级，越大越优先（netrule_register 可选，默认 1）",
            },
            "extension_id": {
                "type": "string",
                "description": "扩展或应用 ID（extmgr_get/extmgr_launch_app/extmgr_set_enabled/extmgr_uninstall 必填）",
            },
            "enabled": {
                "type": "boolean",
                "description": "是否启用（extmgr_set_enabled 必填）",
            },
            "native_host": {
                "type": "string",
                "description": "本机应用（native messaging host）名称（native_send 必填）",
            },
            "proxy_mode": {
                "type": "string",
                "enum": [
                    "direct",
                    "auto_detect",
                    "pac_script",
                    "system",
                    "fixed_servers",
                ],
                "description": "代理模式（proxy_set_settings 必填）",
            },
            "pac_url": {
                "type": "string",
                "description": "PAC 脚本 URL（proxy_set_settings 在 proxy_mode=pac_script 时必填）",
            },
            "proxy_rules": {
                "type": "object",
                "description": "代理规则对象（proxy_set_settings 在 proxy_mode=fixed_servers 时必填）",
            },
            "privacy_area": {
                "type": "string",
                "enum": ["network", "services", "websites"],
                "description": "隐私设置分组（privacy_get/privacy_set 必填）",
            },
            "privacy_name": {
                "type": "string",
                "description": "隐私设置项名，如 networkPredictionEnabled（privacy_get/privacy_set 必填）",
            },
            "privacy_value": {
                "type": "boolean",
                "description": "隐私设置的目标值（privacy_set 必填）",
            },
            "data_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": '要清除的数据类型数组，如 ["cache","cookies","history","downloads","formData","passwords"]'
                "（browsingdata_remove 必填）。**清除不可逆**",
            },
            "since": {
                "type": "integer",
                "description": "清除起始时间，毫秒时间戳（browsingdata_remove 可选，不传则清除全部）",
            },
            "content_type": {
                "type": "string",
                "description": "内容设置类型，如 cookies/javascript/images/popups/geolocation"
                "（contentsettings_get/contentsettings_set/contentsettings_clear 必填）",
            },
            "content_setting": {
                "type": "string",
                "enum": ["allow", "block", "ask", "session_only"],
                "description": "内容设置值（contentsettings_set 必填）",
            },
            "primary_pattern": {
                "type": "string",
                "description": "内容设置主匹配模式，如 https://example.com/*（contentsettings_set 可选）",
            },
            "secondary_pattern": {
                "type": "string",
                "description": "内容设置次匹配模式（contentsettings_set 可选）",
            },
            "primary_url": {
                "type": "string",
                "description": "主 URL（contentsettings_get 可选，不传返回全局默认值）",
            },
            "secondary_url": {
                "type": "string",
                "description": "次 URL（contentsettings_get 可选）",
            },
            "timeout": {
                "type": "number",
                "description": "等待指令执行结果的超时秒数（默认 15）",
            },
        },
        "required": ["action"],
    }

    def _get_master_url(self, action_name: str = "") -> Optional[Dict[str, Any]]:
        """获取 master_url，未设置时返回错误字典。"""
        if not jglobals.master_url:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"master_url is not set, cannot {action_name}. "
                "Please ensure the agent is started with --master-url option.",
            }
        return None

    def _build_auth_headers(self) -> Dict[str, str]:
        """构建带认证信息的请求头。"""
        headers: Dict[str, str] = {}
        auth_token = os.environ.get("JARVIS_AUTH_TOKEN")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    def _request_gateway(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        error_prefix: str = "Request failed",
        timeout: float = 20.0,
    ) -> Dict[str, Any]:
        """向 Gateway 发送 HTTP 请求。"""
        url = f"{jglobals.master_url}{path}"
        headers = self._build_auth_headers()
        try:
            with httpx.Client(timeout=timeout) as client:
                if method.upper() == "POST":
                    response = client.post(url, json=json_data, headers=headers)
                elif method.upper() == "DELETE":
                    response = client.delete(url, headers=headers, params=params)
                else:
                    response = client.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": response.json(),
                }
            return {
                "success": False,
                "status_code": response.status_code,
                "data": None,
                "error": f"{error_prefix}: HTTP {response.status_code} - {response.text}",
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"Cannot connect to gateway at {jglobals.master_url}. "
                "Please ensure the gateway is running.",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"{error_prefix}: {str(e)}",
            }

    def _send_command(
        self,
        session_id: str,
        action: str,
        params: Dict[str, Any],
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """通过网关向浏览器扩展会话下发指令。"""
        result = self._request_gateway(
            "POST",
            "/api/browser-ext/command",
            json_data={
                "session_id": session_id,
                "action": action,
                "params": params,
                "timeout": timeout,
            },
            error_prefix=f"Failed to send {action}",
            timeout=timeout + 5.0,
        )
        if not result.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": result.get("error") or "unknown error",
            }
        data = result.get("data") or {}
        if not data.get("success"):
            return {
                "success": False,
                "stdout": "",
                "stderr": data.get("error") or "command failed",
            }
        # 扩展返回的结果信封：{id, type:"result", success, data, error}
        envelope = data.get("result") or {}
        if not envelope.get("success", False):
            return {
                "success": False,
                "stdout": "",
                "stderr": envelope.get("error") or "extension reported failure",
            }
        return {
            "success": True,
            "stdout": self._format_result(action, envelope.get("data")),
            "stderr": "",
        }

    @staticmethod
    def _format_result(action: str, data: Any) -> str:
        """把扩展返回的数据格式化为可读文本。"""
        import json

        if data is None:
            return f"{action} 执行成功"
        if isinstance(data, str):
            return data
        try:
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            return str(data)

    def _send_command_raw(
        self,
        session_id: str,
        action: str,
        params: Dict[str, Any],
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """通过网关向扩展下发指令，并返回**原始 data**（不做文本格式化）。

        与 `_send_command` 的区别：`_send_command` 会把扩展返回的 data 序列化成
        stdout 文本（对含大段源码的 action 会把源码原文带进上下文），
        本方法保留原始 dict，供需要读取结构化字段（如脚本 source）的调用方使用。

        Returns:
            Dict[str, Any]: 成功时 ``{"success": True, "data": <原始 data>}``；
                失败时 ``{"success": False, "error": str}``
        """
        result = self._request_gateway(
            "POST",
            "/api/browser-ext/command",
            json_data={
                "session_id": session_id,
                "action": action,
                "params": params,
                "timeout": timeout,
            },
            error_prefix=f"Failed to send {action}",
            timeout=timeout + 5.0,
        )
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error") or "unknown error",
            }
        data = result.get("data") or {}
        if not data.get("success"):
            return {"success": False, "error": data.get("error") or "command failed"}
        # 扩展返回的结果信封：{id, type:"result", success, data, error}
        envelope = data.get("result") or {}
        if not envelope.get("success", False):
            return {
                "success": False,
                "error": envelope.get("error") or "extension reported failure",
            }
        return {"success": True, "data": envelope.get("data")}

    def _screenshot_to_file(
        self,
        session_id: str,
        params: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """截图并把 base64 落盘为临时 PNG 文件，stdout 只返回路径与尺寸。"""
        import base64
        import os
        import tempfile
        import time

        result = self._send_command(session_id, "capture.screenshot", params, timeout)
        if not result.get("success"):
            return result

        # _send_command 已把扩展返回的 data 格式化为文本，这里需要原始 data，
        # 因此重新解析 stdout（扩展返回的是 JSON 文本）。
        import json

        try:
            data = json.loads(result.get("stdout") or "{}")
        except Exception:
            return {
                "success": False,
                "stdout": "",
                "stderr": "failed to parse screenshot result",
            }

        image = data.get("image") or data.get("data_url") or data.get("dataUrl") or ""
        if not image:
            return {
                "success": False,
                "stdout": "",
                "stderr": "screenshot result contains no image data",
            }

        if "," in image and image.strip().startswith("data:"):
            image = image.split(",", 1)[1]

        try:
            raw = base64.b64decode(image)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"failed to decode screenshot base64: {e}",
            }

        path = os.path.join(
            tempfile.gettempdir(),
            f"jarvis_browser_ext_{int(time.time() * 1000)}.png",
        )
        try:
            with open(path, "wb") as f:
                f.write(raw)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"failed to write screenshot file: {e}",
            }

        info = {
            "path": path,
            "width": data.get("width"),
            "height": data.get("height"),
            "full_page": bool(params.get("full_page")),
            "bytes": len(raw),
        }
        return {
            "success": True,
            "stdout": json.dumps(info, ensure_ascii=False, indent=2),
            "stderr": "",
        }

    def execute(
        self,
        action: str,
        session_id: Optional[str] = None,
        tab_id: Optional[int] = None,
        url: str = "",
        selector: str = "",
        text: str = "",
        value: str = "",
        state: str = "",
        all: bool = False,
        key: str = "",
        x: Optional[int] = None,
        y: Optional[int] = None,
        behavior: str = "",
        code: str = "",
        world: str = "",
        file_path: str = "",
        full_page: bool = False,
        props: Optional[List[str]] = None,
        expression: str = "",
        await_promise: bool = True,
        method: str = "",
        cdp_params: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        clear: bool = False,
        duration_ms: Optional[int] = None,
        filter: str = "",
        new_window: bool = True,
        script_id: str = "",
        script_action: str = "",
        script_args: Optional[Dict[str, Any]] = None,
        script_name: str = "",
        script_source: str = "",
        script_url: str = "",
        script_description: str = "",
        script_match: Optional[List[str]] = None,
        script_version: str = "",
        script_enabled: Optional[bool] = None,
        clipboard_text: str = "",
        clipboard_base64: str = "",
        clipboard_mime: str = "",
        clipboard_as: str = "",
        clipboard_url: str = "",
        bookmark_query: str = "",
        bookmark_id: str = "",
        parent_id: str = "",
        history_query: str = "",
        history_url: str = "",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        max_results: Optional[int] = None,
        download_query: str = "",
        download_id: Optional[int] = None,
        filename: str = "",
        save_as: bool = True,
        delete_file: bool = False,
        session_key: str = "",
        has_been_read: Optional[bool] = None,
        menu_id: str = "",
        contexts: Optional[List[str]] = None,
        url_patterns: Optional[List[str]] = None,
        alarm_name: str = "",
        delay_minutes: Optional[float] = None,
        period_minutes: Optional[float] = None,
        notification_id: str = "",
        message: str = "",
        icon_url: str = "",
        search_query: str = "",
        disposition: str = "",
        detection_interval_seconds: Optional[int] = None,
        page_url: str = "",
        size: Optional[int] = None,
        frame_id: Optional[int] = None,
        group_id: Optional[int] = None,
        group_title: str = "",
        color: str = "",
        collapsed: Optional[bool] = None,
        window_id: Optional[int] = None,
        cookie_name: str = "",
        domain: str = "",
        path: str = "",
        secure: Optional[bool] = None,
        http_only: Optional[bool] = None,
        same_site: str = "",
        expiration_date: Optional[float] = None,
        rule_id: Optional[int] = None,
        url_filter: str = "",
        action_type: str = "",
        redirect_url: str = "",
        priority: Optional[int] = None,
        extension_id: str = "",
        enabled: Optional[bool] = None,
        native_host: str = "",
        proxy_mode: str = "",
        pac_url: str = "",
        proxy_rules: Optional[Dict[str, Any]] = None,
        privacy_area: str = "",
        privacy_name: str = "",
        privacy_value: Optional[bool] = None,
        data_types: Optional[List[str]] = None,
        since: Optional[int] = None,
        content_type: str = "",
        content_setting: str = "",
        primary_pattern: str = "",
        secondary_pattern: str = "",
        primary_url: str = "",
        secondary_url: str = "",
        timeout: float = 15.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """执行浏览器扩展操作。

        参数:
            action: 操作类型（见 parameters.enum）
            session_id: 浏览器扩展会话 ID（除 list_sessions 外必填）
            tab_id: 目标标签页 ID
            url: 要导航到的 URL（navigate/new_tab）
            selector: CSS 选择器（get_text/click/type/query/get_html/hover/select/wait_for）
            text: 要输入的文本（type）
            value: 下拉框选项的值（select）
            state: 等待的目标状态（wait_for，visible/hidden/attached）
            all: 是否返回全部匹配元素（query）
            timeout: 等待结果的超时秒数
            **kwargs: 其他参数

        返回:
            Dict[str, Any]: {"success": bool, "stdout": str, "stderr": str}
        """
        # 兼容 v1.0 协议：registry 可能将整个参数字典作为 action 传入
        if isinstance(action, dict):
            args = action
            action = args.get("action", "")
            session_id = args.get("session_id")
            tab_id = args.get("tab_id")
            url = args.get("url", "")
            selector = args.get("selector", "")
            text = args.get("text", "")
            value = args.get("value", "")
            state = args.get("state", "")
            all = args.get("all", False)
            key = args.get("key", "")
            x = args.get("x")
            y = args.get("y")
            behavior = args.get("behavior", "")
            code = args.get("code", "")
            world = args.get("world", "")
            file_path = args.get("file_path", "")
            full_page = args.get("full_page", False)
            props = args.get("props")
            expression = args.get("expression", "")
            await_promise = args.get("await_promise", True)
            method = args.get("method", "")
            cdp_params = args.get("cdp_params")
            limit = args.get("limit")
            clear = args.get("clear", False)
            duration_ms = args.get("duration_ms")
            filter = args.get("filter", "")
            script_id = args.get("script_id", "")
            script_action = args.get("script_action", "")
            script_args = args.get("script_args")
            script_name = args.get("script_name", "")
            script_source = args.get("script_source", "")
            script_url = args.get("script_url", "")
            script_description = args.get("script_description", "")
            script_match = args.get("script_match")
            script_version = args.get("script_version", "")
            script_enabled = args.get("script_enabled")
            clipboard_text = args.get("clipboard_text", "")
            clipboard_base64 = args.get("clipboard_base64", "")
            clipboard_mime = args.get("clipboard_mime", "")
            clipboard_as = args.get("clipboard_as", "")
            clipboard_url = args.get("clipboard_url", "")
            bookmark_query = args.get("bookmark_query", "")
            bookmark_id = args.get("bookmark_id", "")
            parent_id = args.get("parent_id", "")
            history_query = args.get("history_query", "")
            history_url = args.get("history_url", "")
            start_time = args.get("start_time")
            end_time = args.get("end_time")
            max_results = args.get("max_results")
            download_query = args.get("download_query", "")
            download_id = args.get("download_id")
            filename = args.get("filename", "")
            save_as = args.get("save_as", True)
            delete_file = args.get("delete_file", False)
            session_key = args.get("session_key", "")
            has_been_read = args.get("has_been_read")
            menu_id = args.get("menu_id", "")
            contexts = args.get("contexts")
            url_patterns = args.get("url_patterns")
            alarm_name = args.get("alarm_name", "")
            delay_minutes = args.get("delay_minutes")
            period_minutes = args.get("period_minutes")
            notification_id = args.get("notification_id", "")
            message = args.get("message", "")
            icon_url = args.get("icon_url", "")
            search_query = args.get("search_query", "")
            disposition = args.get("disposition", "")
            detection_interval_seconds = args.get("detection_interval_seconds")
            page_url = args.get("page_url", "")
            size = args.get("size")
            frame_id = args.get("frame_id")
            group_id = args.get("group_id")
            group_title = args.get("group_title", "")
            color = args.get("color", "")
            collapsed = args.get("collapsed")
            window_id = args.get("window_id")
            cookie_name = args.get("cookie_name", "")
            domain = args.get("domain", "")
            path = args.get("path", "")
            secure = args.get("secure")
            http_only = args.get("http_only")
            same_site = args.get("same_site", "")
            expiration_date = args.get("expiration_date")
            rule_id = args.get("rule_id")
            url_filter = args.get("url_filter", "")
            action_type = args.get("action_type", "")
            redirect_url = args.get("redirect_url", "")
            priority = args.get("priority")
            extension_id = args.get("extension_id", "")
            enabled = args.get("enabled")
            native_host = args.get("native_host", "")
            proxy_mode = args.get("proxy_mode", "")
            pac_url = args.get("pac_url", "")
            proxy_rules = args.get("proxy_rules")
            privacy_area = args.get("privacy_area", "")
            privacy_name = args.get("privacy_name", "")
            privacy_value = args.get("privacy_value")
            data_types = args.get("data_types")
            since = args.get("since")
            content_type = args.get("content_type", "")
            content_setting = args.get("content_setting", "")
            primary_pattern = args.get("primary_pattern", "")
            secondary_pattern = args.get("secondary_pattern", "")
            primary_url = args.get("primary_url", "")
            secondary_url = args.get("secondary_url", "")
            timeout = args.get("timeout", 15.0)

        action = str(action or "").strip()
        if not action:
            return {
                "success": False,
                "stdout": "",
                "stderr": "action is required",
            }

        err = self._get_master_url(f"execute {action}")
        if err is not None:
            return err

        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 15.0

        # ---------------- list_sessions ----------------
        if action == "list_sessions":
            result = self._request_gateway(
                "GET",
                "/api/browser-ext/sessions",
                error_prefix="Failed to list browser sessions",
            )
            if not result.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": result.get("error") or "unknown error",
                }
            data = result.get("data") or {}
            sessions: List[Dict[str, Any]] = data.get("sessions") or []
            if not sessions:
                return {
                    "success": True,
                    "stdout": "当前没有在线的浏览器扩展会话。"
                    "请确认用户已在浏览器中安装并连接 Jarvis Browser Bridge 扩展。",
                    "stderr": "",
                }
            return {
                "success": True,
                "stdout": self._format_result("list_sessions", sessions),
                "stderr": "",
            }

        # ---------------- 其余操作均需 session_id ----------------
        known_actions = {
            "list_tabs",
            "navigate",
            "get_text",
            "click",
            "type",
            "screenshot",
            "activate_tab",
            "close_tab",
            "new_tab",
            "reload",
            "back",
            "forward",
            "query",
            "get_html",
            "hover",
            "select",
            "wait_for",
            "press_key",
            "scroll",
            "execute_script",
            "upload_file",
            "get_computed_style",
            "get_page_info",
            "get_console_logs",
            "evaluate",
            "send_cdp_command",
            "get_network_requests",
            "script_list",
            "script_get",
            "script_run",
            "script_install",
            "script_install_from_url",
            "script_uninstall",
            "script_export",
            "script_set_enabled",
            "script_save",
            "script_load_from_file",
            "clipboard_write",
            "clipboard_write_from_url",
            "bookmark_list",
            "bookmark_search",
            "bookmark_create",
            "bookmark_remove",
            "bookmark_remove_tree",
            "history_search",
            "history_recent",
            "history_remove",
            "history_remove_range",
            "download_list",
            "download_search",
            "download_start",
            "download_pause",
            "download_resume",
            "download_cancel",
            "download_erase",
            "download_open",
            "session_recent",
            "session_restore",
            "topsite_list",
            "readinglist_list",
            "readinglist_add",
            "readinglist_remove",
            "readinglist_update",
            "contextmenu_create",
            "contextmenu_remove",
            "contextmenu_remove_all",
            "contextmenu_list",
            "alarm_create",
            "alarm_list",
            "alarm_clear",
            "alarm_clear_all",
            "notification_create",
            "notification_clear",
            "notification_clear_all",
            "notification_list",
            "search_query",
            "idle_query_state",
            "idle_set_interval",
            "idle_get_interval",
            "favicon_get_url",
            "webnav_get_all_frames",
            "webnav_get_frame",
            "tabgroup_list",
            "tabgroup_get",
            "tabgroup_query",
            "tabgroup_update",
            "cookie_get",
            "cookie_get_all",
            "cookie_set",
            "cookie_remove",
            "netrule_list",
            "netrule_register",
            "netrule_unregister",
            "extmgr_list",
            "extmgr_get",
            "extmgr_launch_app",
            "extmgr_set_enabled",
            "extmgr_uninstall",
            "native_send",
            "proxy_get_settings",
            "proxy_set_settings",
            "proxy_clear_settings",
            "privacy_get",
            "privacy_set",
            "browsingdata_settings",
            "browsingdata_remove",
            "contentsettings_get",
            "contentsettings_set",
            "contentsettings_clear",
        }
        if action not in known_actions:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"unknown action: {action}",
            }

        session_id = str(session_id or "").strip()
        if not session_id:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"session_id is required for action '{action}'. "
                "请先调用 list_sessions 获取。",
            }

        params: Dict[str, Any] = {}
        if tab_id is not None:
            params["tab_id"] = tab_id

        # ---------------- list_tabs ----------------
        if action == "list_tabs":
            return self._send_command(session_id, "tab.list", params, timeout)

        # ---------------- navigate ----------------
        if action == "navigate":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'navigate'",
                }
            params["url"] = url
            if tab_id is None:
                # 未指定 tab_id 时会新建页面，透传 new_window 决定是否新窗口打开
                params["new_window"] = new_window
            return self._send_command(session_id, "page.navigate", params, timeout)

        # ---------------- get_text ----------------
        if action == "get_text":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'get_text'",
                }
            params["selector"] = selector
            return self._send_command(session_id, "dom.get_text", params, timeout)

        # ---------------- click ----------------
        if action == "click":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'click'",
                }
            params["selector"] = selector
            return self._send_command(session_id, "dom.click", params, timeout)

        # ---------------- type ----------------
        if action == "type":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'type'",
                }
            params["selector"] = selector
            params["text"] = text
            return self._send_command(session_id, "dom.type", params, timeout)

        # ---------------- screenshot ----------------
        if action == "screenshot":
            if full_page:
                params["full_page"] = True
            return self._screenshot_to_file(session_id, params, timeout)

        # ---------------- activate_tab ----------------
        if action == "activate_tab":
            if tab_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "tab_id is required for action 'activate_tab'",
                }
            return self._send_command(session_id, "tab.activate", params, timeout)

        # ---------------- close_tab ----------------
        if action == "close_tab":
            if tab_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "tab_id is required for action 'close_tab'",
                }
            return self._send_command(session_id, "tab.close", params, timeout)

        # ---------------- new_tab ----------------
        if action == "new_tab":
            if url:
                params["url"] = url
            params["new_window"] = new_window
            return self._send_command(session_id, "tab.create", params, timeout)

        # ---------------- reload ----------------
        if action == "reload":
            return self._send_command(session_id, "page.reload", params, timeout)

        # ---------------- back ----------------
        if action == "back":
            return self._send_command(session_id, "page.back", params, timeout)

        # ---------------- forward ----------------
        if action == "forward":
            return self._send_command(session_id, "page.forward", params, timeout)

        # ---------------- query ----------------
        if action == "query":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'query'",
                }
            params["selector"] = selector
            if all:
                params["all"] = True
            return self._send_command(session_id, "dom.query", params, timeout)

        # ---------------- get_html ----------------
        if action == "get_html":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'get_html'",
                }
            params["selector"] = selector
            return self._send_command(session_id, "dom.get_html", params, timeout)

        # ---------------- hover ----------------
        if action == "hover":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'hover'",
                }
            params["selector"] = selector
            return self._send_command(session_id, "dom.hover", params, timeout)

        # ---------------- select ----------------
        if action == "select":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'select'",
                }
            if value == "":
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "value is required for action 'select'",
                }
            params["selector"] = selector
            params["value"] = value
            return self._send_command(session_id, "dom.select", params, timeout)

        # ---------------- wait_for ----------------
        if action == "wait_for":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'wait_for'",
                }
            params["selector"] = selector
            if state:
                params["state"] = state
            # wait_for 的等待时长以 timeout 参数为准（秒 → 毫秒）
            params["timeout_ms"] = int(timeout * 1000)
            return self._send_command(session_id, "dom.wait_for", params, timeout)

        # ---------------- press_key ----------------
        if action == "press_key":
            if not key:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "key is required for action 'press_key'",
                }
            params["key"] = key
            if selector:
                params["selector"] = selector
            return self._send_command(session_id, "dom.press_key", params, timeout)

        # ---------------- scroll ----------------
        if action == "scroll":
            if not selector and x is None and y is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "either selector or x/y is required for action 'scroll'",
                }
            if selector:
                params["selector"] = selector
            if x is not None:
                params["x"] = x
            if y is not None:
                params["y"] = y
            if behavior:
                params["behavior"] = behavior
            return self._send_command(session_id, "dom.scroll", params, timeout)

        # ---------------- execute_script ----------------
        if action == "execute_script":
            if not code:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "code is required for action 'execute_script'",
                }
            params["code"] = code
            if world:
                params["world"] = world
            return self._send_command(session_id, "script.execute", params, timeout)

        # ---------------- upload_file ----------------
        if action == "upload_file":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'upload_file'",
                }
            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "file_path is required for action 'upload_file'",
                }
            params["selector"] = selector
            params["file_path"] = file_path
            return self._send_command(session_id, "dom.upload_file", params, timeout)

        # ---------------- get_computed_style ----------------
        if action == "get_computed_style":
            if not selector:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "selector is required for action 'get_computed_style'",
                }
            params["selector"] = selector
            if props:
                params["props"] = list(props)
            return self._send_command(
                session_id, "dom.get_computed_style", params, timeout
            )

        # ---------------- get_page_info ----------------
        if action == "get_page_info":
            return self._send_command(session_id, "page.get_info", params, timeout)

        # ---------------- get_console_logs ----------------
        if action == "get_console_logs":
            if limit is not None:
                params["limit"] = int(limit)
            if clear:
                params["clear"] = True
            return self._send_command(session_id, "console.get_logs", params, timeout)

        # ---------------- evaluate ----------------
        if action == "evaluate":
            if not expression:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "expression is required for action 'evaluate'",
                }
            params["expression"] = expression
            params["await_promise"] = bool(await_promise)
            return self._send_command(session_id, "debugger.evaluate", params, timeout)

        # ---------------- send_cdp_command ----------------
        if action == "send_cdp_command":
            if not method:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "method is required for action 'send_cdp_command'",
                }
            params["method"] = method
            if cdp_params:
                params["params"] = dict(cdp_params)
            return self._send_command(
                session_id, "debugger.send_command", params, timeout
            )

        # ---------------- get_network_requests ----------------
        if action == "get_network_requests":
            if duration_ms is not None:
                params["duration_ms"] = int(duration_ms)
            if limit is not None:
                params["limit"] = int(limit)
            if filter:
                params["filter"] = filter
            # 采集时长可能超过默认 timeout，自动放宽
            collect_ms = int(duration_ms) if duration_ms else 3000
            net_timeout = max(timeout, collect_ms / 1000.0 + 5.0)
            return self._send_command(
                session_id, "network.get_requests", params, net_timeout
            )

        # ---------------- script_list ----------------
        if action == "script_list":
            return self._send_command(session_id, "script.list", params, timeout)

        # ---------------- script_get ----------------
        if action == "script_get":
            if not script_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_id is required for action 'script_get'",
                }
            params["id"] = script_id
            return self._send_command(session_id, "script.get", params, timeout)

        # ---------------- script_run ----------------
        if action == "script_run":
            if not script_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_id is required for action 'script_run'",
                }
            if not script_action:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_action is required for action 'script_run'",
                }
            # 扩展侧 script.run 的 params 为 { id, action, args, tab_id }
            params["id"] = script_id
            params["action"] = script_action
            params["args"] = dict(script_args) if script_args else {}
            return self._send_command(session_id, "script.run", params, timeout)

        # ---------------- script_install ----------------
        if action == "script_install":
            if not script_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_name is required for action 'script_install'",
                }
            if not script_source:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_source is required for action 'script_install'",
                }
            # 扩展侧 script.install 的 params 为 { name, source, description, match, version }
            params["name"] = script_name
            params["source"] = script_source
            if script_description:
                params["description"] = script_description
            if script_match:
                params["match"] = list(script_match)
            if script_version:
                params["version"] = script_version
            return self._send_command(session_id, "script.install", params, timeout)

        # ---------------- script_install_from_url ----------------
        if action == "script_install_from_url":
            if not script_url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_url is required for action 'script_install_from_url'",
                }
            # 扩展侧 script.install_from_url 的 params 为
            # { url, name, description, match, version }，源码由扩展后台 fetch
            params["url"] = script_url
            if script_name:
                params["name"] = script_name
            if script_description:
                params["description"] = script_description
            if script_match:
                params["match"] = list(script_match)
            if script_version:
                params["version"] = script_version
            return self._send_command(
                session_id, "script.install_from_url", params, timeout
            )

        # ---------------- script_uninstall ----------------
        if action == "script_uninstall":
            if not script_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_id is required for action 'script_uninstall'",
                }
            params["id"] = script_id
            return self._send_command(session_id, "script.uninstall", params, timeout)

        # ---------------- script_export ----------------
        if action == "script_export":
            if not script_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_id is required for action 'script_export'",
                }
            params["id"] = script_id
            return self._send_command(session_id, "script.export", params, timeout)

        # ---------------- script_set_enabled ----------------
        if action == "script_set_enabled":
            if not script_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_id is required for action 'script_set_enabled'",
                }
            if script_enabled is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_enabled is required for action 'script_set_enabled'",
                }
            params["id"] = script_id
            params["enabled"] = bool(script_enabled)
            return self._send_command(session_id, "script.set_enabled", params, timeout)

        # ---------------- script_save ----------------
        if action == "script_save":
            if not script_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_id is required for action 'script_save'",
                }
            # 1) 从扩展导出脚本（取原始 data，避免源码进入 stdout）
            exported = self._send_command_raw(
                session_id, "script.export", {"id": script_id}, timeout
            )
            if not exported.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": exported.get("error") or "failed to export script",
                }
            exp_data = exported.get("data") or {}
            content = exp_data.get("content") or ""
            if not content:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "exported script has empty content",
                }
            save_name = (script_name or exp_data.get("name") or "").strip()
            if not save_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script name is required (pass script_name or ensure the "
                    "installed script has a name)",
                }
            # 2) 落到网关数据目录
            saved = self._request_gateway(
                "POST",
                "/api/browser-ext/scripts/save",
                json_data={"name": save_name, "content": content},
                error_prefix="Failed to save script file",
            )
            if not saved.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": saved.get("error") or "failed to save script file",
                }
            saved_data = saved.get("data") or {}
            if not saved_data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": saved_data.get("error") or "failed to save script file",
                }
            # 只回传路径与大小，不回传脚本原文
            info = {
                "name": saved_data.get("name") or save_name,
                "path": saved_data.get("path"),
                "size": saved_data.get("size"),
            }
            return {
                "success": True,
                "stdout": "已保存脚本到网关目录："
                + json.dumps(info, ensure_ascii=False, indent=2),
                "stderr": "",
            }

        # ---------------- script_load_from_file ----------------
        if action == "script_load_from_file":
            if not script_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "script_name is required for action 'script_load_from_file'",
                }
            # 1) 从网关目录读取脚本
            loaded = self._request_gateway(
                "GET",
                "/api/browser-ext/scripts/load",
                params={"name": script_name},
                error_prefix="Failed to load script file",
            )
            if not loaded.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": loaded.get("error") or "failed to load script file",
                }
            loaded_data = loaded.get("data") or {}
            if not loaded_data.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": loaded_data.get("error") or "failed to load script file",
                }
            content = loaded_data.get("content") or ""
            if not content:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"script file '{script_name}' is empty",
                }
            # 2) 安装到扩展
            install_params: Dict[str, Any] = {
                "name": script_name,
                "source": content,
            }
            if script_description:
                install_params["description"] = script_description
            if script_match:
                install_params["match"] = list(script_match)
            if script_version:
                install_params["version"] = script_version
            installed = self._send_command_raw(
                session_id, "script.install", install_params, timeout
            )
            if not installed.get("success"):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": installed.get("error") or "failed to install script",
                }
            # 只回传元数据，不回传脚本原文
            meta = installed.get("data") or {}
            return {
                "success": True,
                "stdout": "已从网关目录安装脚本："
                + json.dumps(meta, ensure_ascii=False, indent=2),
                "stderr": "",
            }

        # ---------------- clipboard_write ----------------
        if action == "clipboard_write":
            # 扩展侧 clipboard.write 的 params 为 { text, base64, mime, as, tab_id }
            if clipboard_as:
                params["as"] = clipboard_as
            if clipboard_text:
                params["text"] = clipboard_text
            if clipboard_base64:
                params["base64"] = clipboard_base64
            if clipboard_mime:
                params["mime"] = clipboard_mime
            if not clipboard_text and not clipboard_base64:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "clipboard_text or clipboard_base64 is required "
                    "for action 'clipboard_write'",
                }
            return self._send_command(session_id, "clipboard.write", params, timeout)

        # ---------------- clipboard_write_from_url ----------------
        if action == "clipboard_write_from_url":
            if not clipboard_url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "clipboard_url is required for action 'clipboard_write_from_url'",
                }
            # 扩展侧 clipboard.writeFromUrl 的 params 为 { url, as, mime, tab_id }
            params["url"] = clipboard_url
            if clipboard_as:
                params["as"] = clipboard_as
            if clipboard_mime:
                params["mime"] = clipboard_mime
            return self._send_command(
                session_id, "clipboard.write_from_url", params, timeout
            )

        # ---------------- bookmark_list ----------------
        if action == "bookmark_list":
            if parent_id:
                params["parent_id"] = parent_id
            return self._send_command(session_id, "bookmark.list", params, timeout)

        # ---------------- bookmark_search ----------------
        if action == "bookmark_search":
            if not bookmark_query:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "bookmark_query is required for action 'bookmark_search'",
                }
            params["query"] = bookmark_query
            if max_results is not None:
                params["max_results"] = max_results
            return self._send_command(session_id, "bookmark.search", params, timeout)

        # ---------------- bookmark_create ----------------
        if action == "bookmark_create":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'bookmark_create'",
                }
            params["url"] = url
            if text:
                params["title"] = text
            if parent_id:
                params["parent_id"] = parent_id
            return self._send_command(session_id, "bookmark.create", params, timeout)

        # ---------------- bookmark_remove ----------------
        if action == "bookmark_remove":
            if not bookmark_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "bookmark_id is required for action 'bookmark_remove'",
                }
            params["id"] = bookmark_id
            return self._send_command(session_id, "bookmark.remove", params, timeout)

        # ---------------- bookmark_remove_tree ----------------
        if action == "bookmark_remove_tree":
            if not bookmark_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "bookmark_id is required for action 'bookmark_remove_tree'",
                }
            params["id"] = bookmark_id
            return self._send_command(
                session_id, "bookmark.remove_tree", params, timeout
            )

        # ---------------- history_search ----------------
        if action == "history_search":
            if history_query:
                params["query"] = history_query
            if start_time is not None:
                params["start_time"] = start_time
            if end_time is not None:
                params["end_time"] = end_time
            if max_results is not None:
                params["max_results"] = max_results
            return self._send_command(session_id, "history.search", params, timeout)

        # ---------------- history_recent ----------------
        if action == "history_recent":
            if max_results is not None:
                params["max_results"] = max_results
            return self._send_command(session_id, "history.recent", params, timeout)

        # ---------------- history_remove ----------------
        if action == "history_remove":
            if not history_url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "history_url is required for action 'history_remove'",
                }
            params["url"] = history_url
            return self._send_command(session_id, "history.remove", params, timeout)

        # ---------------- history_remove_range ----------------
        if action == "history_remove_range":
            if start_time is not None:
                params["start_time"] = start_time
            if end_time is not None:
                params["end_time"] = end_time
            return self._send_command(
                session_id, "history.remove_range", params, timeout
            )

        # ---------------- download_list ----------------
        if action == "download_list":
            if download_query:
                params["query"] = download_query
            if max_results is not None:
                params["limit"] = int(max_results)
            return self._send_command(session_id, "download.list", params, timeout)

        # ---------------- download_search ----------------
        if action == "download_search":
            if not download_query:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "download_query is required for action 'download_search'",
                }
            params["query"] = download_query
            if max_results is not None:
                params["limit"] = int(max_results)
            return self._send_command(session_id, "download.search", params, timeout)

        # ---------------- download_start ----------------
        if action == "download_start":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'download_start'",
                }
            params["url"] = url
            if filename:
                params["filename"] = filename
            params["save_as"] = bool(save_as)
            return self._send_command(session_id, "download.start", params, timeout)

        # ---------------- download_pause/resume/cancel/erase/open ----------------
        if action in (
            "download_pause",
            "download_resume",
            "download_cancel",
            "download_erase",
            "download_open",
        ):
            if download_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"download_id is required for action '{action}'",
                }
            params["download_id"] = int(download_id)
            if action == "download_erase" and delete_file:
                params["delete_file"] = True
            ext_action = {
                "download_pause": "download.pause",
                "download_resume": "download.resume",
                "download_cancel": "download.cancel",
                "download_erase": "download.erase",
                "download_open": "download.open",
            }[action]
            return self._send_command(session_id, ext_action, params, timeout)

        # ---------------- session_recent ----------------
        if action == "session_recent":
            if max_results is not None:
                params["max_results"] = int(max_results)
            return self._send_command(session_id, "session.recent", params, timeout)

        # ---------------- session_restore ----------------
        if action == "session_restore":
            if not session_key:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "session_key is required for action 'session_restore'",
                }
            params["session_id"] = session_key
            return self._send_command(session_id, "session.restore", params, timeout)

        # ---------------- topsite_list ----------------
        if action == "topsite_list":
            return self._send_command(session_id, "topsite.list", params, timeout)

        # ---------------- readinglist_list ----------------
        if action == "readinglist_list":
            return self._send_command(session_id, "readinglist.list", params, timeout)

        # ---------------- readinglist_add ----------------
        if action == "readinglist_add":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'readinglist_add'",
                }
            params["url"] = url
            if text:
                params["title"] = text
            if has_been_read is not None:
                params["has_been_read"] = bool(has_been_read)
            return self._send_command(session_id, "readinglist.add", params, timeout)

        # ---------------- readinglist_remove ----------------
        if action == "readinglist_remove":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'readinglist_remove'",
                }
            params["url"] = url
            return self._send_command(session_id, "readinglist.remove", params, timeout)

        # ---------------- readinglist_update ----------------
        if action == "readinglist_update":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'readinglist_update'",
                }
            params["url"] = url
            if has_been_read is not None:
                params["has_been_read"] = bool(has_been_read)
            if text:
                params["title"] = text
            return self._send_command(session_id, "readinglist.update", params, timeout)

        # ---------------- contextmenu_create ----------------
        if action == "contextmenu_create":
            if not menu_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "menu_id is required for action 'contextmenu_create'",
                }
            if not text:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "text is required as menu title for action 'contextmenu_create'",
                }
            params["menu_id"] = menu_id
            params["title"] = text
            if contexts:
                params["contexts"] = list(contexts)
            if url_patterns:
                params["url_patterns"] = list(url_patterns)
            return self._send_command(session_id, "contextmenu.create", params, timeout)

        # ---------------- contextmenu_remove ----------------
        if action == "contextmenu_remove":
            if not menu_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "menu_id is required for action 'contextmenu_remove'",
                }
            params["menu_id"] = menu_id
            return self._send_command(session_id, "contextmenu.remove", params, timeout)

        # ---------------- contextmenu_remove_all ----------------
        if action == "contextmenu_remove_all":
            return self._send_command(
                session_id, "contextmenu.remove_all", params, timeout
            )

        # ---------------- contextmenu_list ----------------
        if action == "contextmenu_list":
            return self._send_command(session_id, "contextmenu.list", params, timeout)

        # ---------------- alarm_create ----------------
        if action == "alarm_create":
            if not alarm_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "alarm_name is required for action 'alarm_create'",
                }
            params["name"] = alarm_name
            if delay_minutes is not None:
                params["delay_minutes"] = float(delay_minutes)
            if period_minutes is not None:
                params["period_minutes"] = float(period_minutes)
            return self._send_command(session_id, "alarm.create", params, timeout)

        # ---------------- alarm_list ----------------
        if action == "alarm_list":
            return self._send_command(session_id, "alarm.list", params, timeout)

        # ---------------- alarm_clear ----------------
        if action == "alarm_clear":
            if not alarm_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "alarm_name is required for action 'alarm_clear'",
                }
            params["name"] = alarm_name
            return self._send_command(session_id, "alarm.clear", params, timeout)

        # ---------------- alarm_clear_all ----------------
        if action == "alarm_clear_all":
            return self._send_command(session_id, "alarm.clear_all", params, timeout)

        # ---------------- notification_create ----------------
        if action == "notification_create":
            if not text:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "text is required as notification title for action 'notification_create'",
                }
            params["title"] = text
            if notification_id:
                params["notification_id"] = notification_id
            if message:
                params["message"] = message
            if icon_url:
                params["icon_url"] = icon_url
            return self._send_command(
                session_id, "notification.create", params, timeout
            )

        # ---------------- notification_clear ----------------
        if action == "notification_clear":
            if not notification_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "notification_id is required for action 'notification_clear'",
                }
            params["notification_id"] = notification_id
            return self._send_command(session_id, "notification.clear", params, timeout)

        # ---------------- notification_clear_all ----------------
        if action == "notification_clear_all":
            return self._send_command(
                session_id, "notification.clear_all", params, timeout
            )

        # ---------------- notification_list ----------------
        if action == "notification_list":
            return self._send_command(session_id, "notification.list", params, timeout)

        # ---------------- search_query ----------------
        if action == "search_query":
            if not search_query:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "search_query is required for action 'search_query'",
                }
            params["query"] = search_query
            if disposition:
                params["disposition"] = disposition
            return self._send_command(session_id, "search.query", params, timeout)

        # ---------------- idle_query_state ----------------
        if action == "idle_query_state":
            if detection_interval_seconds is not None:
                params["detection_interval_seconds"] = int(detection_interval_seconds)
            return self._send_command(session_id, "idle.query_state", params, timeout)

        # ---------------- idle_set_interval ----------------
        if action == "idle_set_interval":
            if detection_interval_seconds is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "detection_interval_seconds is required for action 'idle_set_interval'",
                }
            params["detection_interval_seconds"] = int(detection_interval_seconds)
            return self._send_command(session_id, "idle.set_interval", params, timeout)

        # ---------------- idle_get_interval ----------------
        if action == "idle_get_interval":
            return self._send_command(session_id, "idle.get_interval", params, timeout)

        # ---------------- favicon_get_url ----------------
        if action == "favicon_get_url":
            if not page_url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "page_url is required for action 'favicon_get_url'",
                }
            params["page_url"] = page_url
            if size is not None:
                params["size"] = int(size)
            return self._send_command(session_id, "favicon.get_url", params, timeout)

        # ---------------- webnav_get_all_frames ----------------
        if action == "webnav_get_all_frames":
            if tab_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "tab_id is required for action 'webnav_get_all_frames'",
                }
            return self._send_command(
                session_id, "webnav.get_all_frames", params, timeout
            )

        # ---------------- webnav_get_frame ----------------
        if action == "webnav_get_frame":
            if tab_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "tab_id is required for action 'webnav_get_frame'",
                }
            if frame_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "frame_id is required for action 'webnav_get_frame'",
                }
            params["frame_id"] = int(frame_id)
            return self._send_command(session_id, "webnav.get_frame", params, timeout)

        # ---------------- tabgroup_list ----------------
        if action == "tabgroup_list":
            return self._send_command(session_id, "tabgroup.list", params, timeout)

        # ---------------- tabgroup_get ----------------
        if action == "tabgroup_get":
            if group_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "group_id is required for action 'tabgroup_get'",
                }
            params["group_id"] = int(group_id)
            return self._send_command(session_id, "tabgroup.get", params, timeout)

        # ---------------- tabgroup_query ----------------
        if action == "tabgroup_query":
            if group_title:
                params["title"] = group_title
            if color:
                params["color"] = color
            if window_id is not None:
                params["window_id"] = int(window_id)
            return self._send_command(session_id, "tabgroup.query", params, timeout)

        # ---------------- tabgroup_update ----------------
        if action == "tabgroup_update":
            if group_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "group_id is required for action 'tabgroup_update'",
                }
            params["group_id"] = int(group_id)
            if group_title:
                params["title"] = group_title
            if color:
                params["color"] = color
            if collapsed is not None:
                params["collapsed"] = bool(collapsed)
            return self._send_command(session_id, "tabgroup.update", params, timeout)

        # ================= 以下为高敏感操作，调用前必须向用户确认 =================

        # ---------------- cookie_get ----------------
        if action == "cookie_get":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'cookie_get'",
                }
            if not cookie_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "cookie_name is required for action 'cookie_get'",
                }
            params["url"] = url
            params["name"] = cookie_name
            return self._send_command(session_id, "cookie.get", params, timeout)

        # ---------------- cookie_get_all ----------------
        if action == "cookie_get_all":
            if url:
                params["url"] = url
            if domain:
                params["domain"] = domain
            return self._send_command(session_id, "cookie.get_all", params, timeout)

        # ---------------- cookie_set ----------------
        if action == "cookie_set":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'cookie_set'",
                }
            if not cookie_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "cookie_name is required for action 'cookie_set'",
                }
            params["url"] = url
            params["name"] = cookie_name
            params["value"] = value
            if domain:
                params["domain"] = domain
            if path:
                params["path"] = path
            if secure is not None:
                params["secure"] = bool(secure)
            if http_only is not None:
                params["http_only"] = bool(http_only)
            if same_site:
                params["same_site"] = same_site
            if expiration_date is not None:
                params["expiration_date"] = float(expiration_date)
            return self._send_command(session_id, "cookie.set", params, timeout)

        # ---------------- cookie_remove ----------------
        if action == "cookie_remove":
            if not url:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url is required for action 'cookie_remove'",
                }
            if not cookie_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "cookie_name is required for action 'cookie_remove'",
                }
            params["url"] = url
            params["name"] = cookie_name
            return self._send_command(session_id, "cookie.remove", params, timeout)

        # ---------------- netrule_list ----------------
        if action == "netrule_list":
            return self._send_command(session_id, "netrule.list", params, timeout)

        # ---------------- netrule_register ----------------
        if action == "netrule_register":
            if rule_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "rule_id is required for action 'netrule_register'",
                }
            if not url_filter:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "url_filter is required for action 'netrule_register'",
                }
            params["rule_id"] = int(rule_id)
            params["url_filter"] = url_filter
            if action_type:
                params["action_type"] = action_type
            if redirect_url:
                params["redirect_url"] = redirect_url
            if priority is not None:
                params["priority"] = int(priority)
            return self._send_command(session_id, "netrule.register", params, timeout)

        # ---------------- netrule_unregister ----------------
        if action == "netrule_unregister":
            if rule_id is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "rule_id is required for action 'netrule_unregister'",
                }
            params["rule_id"] = int(rule_id)
            return self._send_command(session_id, "netrule.unregister", params, timeout)

        # ---------------- extmgr_list ----------------
        if action == "extmgr_list":
            return self._send_command(session_id, "extmgr.list", params, timeout)

        # ---------------- extmgr_get ----------------
        if action == "extmgr_get":
            if not extension_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "extension_id is required for action 'extmgr_get'",
                }
            params["extension_id"] = extension_id
            return self._send_command(session_id, "extmgr.get", params, timeout)

        # ---------------- extmgr_launch_app ----------------
        if action == "extmgr_launch_app":
            if not extension_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "extension_id is required for action 'extmgr_launch_app'",
                }
            params["extension_id"] = extension_id
            return self._send_command(session_id, "extmgr.launch_app", params, timeout)

        # ---------------- extmgr_set_enabled ----------------
        if action == "extmgr_set_enabled":
            if not extension_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "extension_id is required for action 'extmgr_set_enabled'",
                }
            if enabled is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "enabled is required for action 'extmgr_set_enabled'",
                }
            params["extension_id"] = extension_id
            params["enabled"] = bool(enabled)
            return self._send_command(session_id, "extmgr.set_enabled", params, timeout)

        # ---------------- extmgr_uninstall ----------------
        if action == "extmgr_uninstall":
            if not extension_id:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "extension_id is required for action 'extmgr_uninstall'",
                }
            params["extension_id"] = extension_id
            return self._send_command(session_id, "extmgr.uninstall", params, timeout)

        # ---------------- native_send ----------------
        if action == "native_send":
            if not native_host:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "native_host is required for action 'native_send'",
                }
            params["native_host"] = native_host
            params["message"] = message
            return self._send_command(session_id, "native.send", params, timeout)

        # ---------------- proxy_get_settings ----------------
        if action == "proxy_get_settings":
            return self._send_command(session_id, "proxy.get_settings", params, timeout)

        # ---------------- proxy_set_settings ----------------
        if action == "proxy_set_settings":
            if not proxy_mode:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "proxy_mode is required for action 'proxy_set_settings'",
                }
            params["mode"] = proxy_mode
            if pac_url:
                params["pac_url"] = pac_url
            if proxy_rules:
                params["rules"] = dict(proxy_rules)
            return self._send_command(session_id, "proxy.set_settings", params, timeout)

        # ---------------- proxy_clear_settings ----------------
        if action == "proxy_clear_settings":
            return self._send_command(
                session_id, "proxy.clear_settings", params, timeout
            )

        # ---------------- privacy_get ----------------
        if action == "privacy_get":
            if not privacy_area:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "privacy_area is required for action 'privacy_get'",
                }
            if not privacy_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "privacy_name is required for action 'privacy_get'",
                }
            params["area"] = privacy_area
            params["name"] = privacy_name
            return self._send_command(session_id, "privacy.get", params, timeout)

        # ---------------- privacy_set ----------------
        if action == "privacy_set":
            if not privacy_area:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "privacy_area is required for action 'privacy_set'",
                }
            if not privacy_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "privacy_name is required for action 'privacy_set'",
                }
            if privacy_value is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "privacy_value is required for action 'privacy_set'",
                }
            params["area"] = privacy_area
            params["name"] = privacy_name
            params["value"] = bool(privacy_value)
            return self._send_command(session_id, "privacy.set", params, timeout)

        # ---------------- browsingdata_settings ----------------
        if action == "browsingdata_settings":
            return self._send_command(
                session_id, "browsingdata.settings", params, timeout
            )

        # ---------------- browsingdata_remove ----------------
        if action == "browsingdata_remove":
            if not data_types:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "data_types is required for action 'browsingdata_remove'",
                }
            params["data_types"] = list(data_types)
            if since is not None:
                params["since"] = int(since)
            return self._send_command(
                session_id, "browsingdata.remove", params, timeout
            )

        # ---------------- contentsettings_get ----------------
        if action == "contentsettings_get":
            if not content_type:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "content_type is required for action 'contentsettings_get'",
                }
            params["content_type"] = content_type
            if primary_url:
                params["primary_url"] = primary_url
            if secondary_url:
                params["secondary_url"] = secondary_url
            return self._send_command(
                session_id, "contentsettings.get", params, timeout
            )

        # ---------------- contentsettings_set ----------------
        if action == "contentsettings_set":
            if not content_type:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "content_type is required for action 'contentsettings_set'",
                }
            if not content_setting:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "content_setting is required for action 'contentsettings_set'",
                }
            params["content_type"] = content_type
            params["setting"] = content_setting
            if primary_pattern:
                params["primary_pattern"] = primary_pattern
            if secondary_pattern:
                params["secondary_pattern"] = secondary_pattern
            return self._send_command(
                session_id, "contentsettings.set", params, timeout
            )

        # ---------------- contentsettings_clear ----------------
        if action == "contentsettings_clear":
            if not content_type:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "content_type is required for action 'contentsettings_clear'",
                }
            params["content_type"] = content_type
            return self._send_command(
                session_id, "contentsettings.clear", params, timeout
            )

        return {
            "success": False,
            "stdout": "",
            "stderr": f"unknown action: {action}",
        }

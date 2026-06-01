# Playwright 浏览器工具功能规范

## 功能概述

提供一个基于 Playwright 的浏览器自动化工具，支持创建持久化浏览器会话、执行页面操作、自动保存页面内容等功能。与 execute_script 和 read_webpage 不同，此工具创建持久会话，可以在多次操作间保持浏览器状态，适用于需要多步交互的场景。

**使用场景**：

- 需要多步骤交互的网站操作
- 需要保持登录状态的操作
- 需要动态加载内容的网页
- 需要执行 JavaScript 的网页

## 接口定义

### 工具类签名

```python
class PlaywrightBrowserTool:
    name = "playwright_browser"
    description = "控制浏览器执行自动化操作（如导航、点击、输入等）。与execute_script不同，此工具创建持久会话，保持浏览器状态。"
    parameters = {...}

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]
```

### 参数定义

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "description": "要执行的浏览器操作类型",
      "enum": [
        "launch",
        "navigate",
        "click",
        "type",
        "screenshot",
        "close",
        "list"
      ]
    },
    "browser_id": {
      "type": "string",
      "description": "浏览器的唯一标识符（默认'default'）"
    },
    "url": {
      "type": "string",
      "description": "要导航的 URL（仅 action=navigate 时有效）"
    },
    "selector": {
      "type": "string",
      "description": "元素选择器（仅 action=click 或 action=type 时有效）"
    },
    "text": {
      "type": "string",
      "description": "要输入的文本（仅 action=type 时有效）"
    },
    "wait_condition": {
      "type": "string",
      "description": "等待条件（默认'network_idle'），可选: 'network_idle', 'timeout'"
    },
    "timeout": {
      "type": "number",
      "description": "超时时间（秒，默认30.0），当 wait_condition=timeout 时使用"
    },
    "content_mode": {
      "type": "string",
      "description": "内容保存模式（默认'abstract'），可选: 'html', 'abstract'"
    },
    "headless": {
      "type": "boolean",
      "description": "是否以无头模式启动浏览器（仅 action=launch 时有效，默认true）"
    }
  },
  "required": ["action"]
}
```

## 输入输出说明

### 通用返回值格式

所有操作返回统一的字典格式：

```python
{
    "success": bool,          # 操作是否成功
    "stdout": str,            # 成功消息或操作结果
    "stderr": str,            # 错误消息或空字符串
    "output_files": List[str]  # 保存的临时文件路径列表
}
```

### 参数详细说明

#### action（必需）

- `launch`: 启动新的浏览器会话
- `navigate`: 导航到指定 URL
- `click`: 点击指定元素
- `type`: 在指定元素中输入文本
- `screenshot`: 截取当前页面截图
- `close`: 关闭浏览器会话
- `list`: 列出所有浏览器会话

#### browser_id（可选）

- 默认值：`"default"`
- 用于标识不同的浏览器实例
- 允许同时运行多个独立的浏览器会话

#### url（仅 action=navigate 时有效）

- 要导航的目标 URL
- 必须是有效的 HTTP/HTTPS URL

#### selector（仅 action=click 或 action=type 时有效）

- 元素选择器，支持 CSS 选择器和 XPath
- 示例：`"button#submit"`, `"input[name='username']"`, `"//div[@class='item']"`

#### text（仅 action=type 时有效）

- 要输入的文本内容
- 会在指定元素中清空原有内容后输入

#### wait_condition（可选）

- 默认值：`"network_idle"`
- `network_idle`: 等待页面所有网络请求完成（至少 500ms 内无网络活动）
- `timeout`: 固定等待指定的超时时间

#### timeout（可选）

- 默认值：`30.0`
- 等待的超时时间（秒）
- 当 wait_condition=timeout 时，直接等待此时间
- 当 wait_condition=network_idle 时，这是最大等待时间

#### content_mode（可选）

- 默认值：`"abstract"`
- `html`: 保存完整的页面 HTML 到文件
- `abstract`: 提取可交互控件，以结构化格式保存到文件

#### headless（仅 action=launch 时有效）

- 默认值：`true`
- `true`: 无头模式，不显示浏览器窗口
- `false`: 显示浏览器窗口（调试用）

## 功能行为

### 1. launch - 启动浏览器

**行为描述**：

- 创建新的浏览器实例（Chromium）
- 创建新的浏览器上下文（Context）
- 创建新的页面（Page）
- 将页面内容保存到临时文件
- 返回临时文件路径

**边界条件**：

- 如果指定的 browser_id 已存在，先关闭旧会话再创建新的
- 如果 headless=false，会显示浏览器窗口

**异常处理**：

- 如果 Playwright 未安装，返回错误提示
- 如果浏览器驱动未安装，返回错误提示

### 2. navigate - 导航到 URL

**行为描述**：

- 导航到指定的 URL
- 根据等待条件等待页面加载完成
- 将页面内容保存到临时文件
- 返回临时文件路径

**等待逻辑**：

- `network_idle`: 调用 `page.wait_for_load_state("networkidle")`，并在超时前返回
- `timeout`: 调用 `page.wait_for_timeout(timeout * 1000)`

**边界条件**：

- URL 必须以 http:// 或 https:// 开头
- 如果 URL 无效，返回错误信息
- 如果浏览器未启动，返回错误信息

### 3. click - 点击元素

**行为描述**：

- 使用选择器查找元素
- 等待元素可见和可点击
- 点击元素
- 根据等待条件等待页面响应
- 将页面内容保存到临时文件
- 返回临时文件路径

**边界条件**：

- 元素必须在页面上存在
- 元素必须是可见和可点击的
- 如果元素不存在，返回错误信息

### 4. type - 输入文本

**行为描述**：

- 使用选择器查找元素
- 等待元素可见
- 清空元素中原有内容
- 输入指定文本
- 将页面内容保存到临时文件
- 返回临时文件路径

**边界条件**：

- 元素必须是输入类型（input、textarea 等）
- 如果元素不存在，返回错误信息

### 5. screenshot - 截图

**行为描述**：

- 截取当前页面的完整截图
- 将截图保存到临时文件
- 返回临时文件路径

**边界条件**：

- 如果浏览器未启动，返回错误信息

### 6. close - 关闭浏览器

**行为描述**：

- 关闭指定 browser_id 的浏览器会话
- 清理相关资源
- 不返回 output_files（因为没有内容需要保存）

**边界条件**：

- 如果浏览器未启动，返回成功（视为已关闭）

### 7. list - 列出浏览器会话

**行为描述**：

- 列出所有活跃的浏览器会话
- 返回每个会话的详细信息
- 不返回 output_files

**返回信息**：

- browser_id
- 状态（活跃/关闭）
- 页面标题
- 页面 URL

## 内容保存模式

### HTML 模式

**行为**：

- 直接调用 `page.content()` 获取完整 HTML
- 写入临时文件（文件名：`<browser_id>_<action>_<timestamp>.html`）

**优点**：

- 保留所有页面细节
- 可用于调试和分析

**缺点**：

- 文件可能很大
- 不易搜索和浏览

### 抽象模式（推荐）

**行为**：

- 提取页面的可交互控件
- 格式化为易读的文本格式
- 写入临时文件（文件名：`<browser_id>_<action>_<timestamp>.txt`）

**提取元素类型**：

- 链接（<a>）
- 按钮（<button>、<input type="button">、<input type="submit">）
- 输入框（<input type="text">、<input type="email">、<input type="password">、<textarea>）
- 选择框（<select>）
- 复选框（<input type="checkbox">）
- 单选框（<input type="radio">）

**输出格式**：

```
操作: navigate
URL: https://example.com
时间: 2024-01-01 12:00:00

=== 可交互控件 ===

[链接] 首页 -> a[href="/home"]
  文本: "返回首页"

[按钮] 提交 -> button#submit
  文本: "提交表单"

[输入] 用户名 -> input[name="username"]
  类型: text

[输入] 密码 -> input[name="password"]
  类型: password

[选择] 国家 -> select#country
  选项: 中国, 美国, 日本
```

**优点**：

- 易于搜索（可用 grep）
- 文件大小适中
- 突出可操作元素

## 临时文件管理

### 文件命名规则

```
格式: <browser_id>_<action>_<timestamp>.<ext>

示例:
  default_launch_20240101_120000.html
  default_navigate_20240101_120500.txt
  default_click_20240101_121000.txt
```

### 文件存储位置

- 默认使用系统临时目录：`/tmp/playwright_browser/`
- 如果目录不存在，自动创建

### 清理建议

- 用户应定期清理临时文件
- close 操作不会自动删除文件（保留调试用途）
- 建议用户手动清理旧文件

## 验收标准

### 1. 功能完整性

- [ ] 所有操作（launch, navigate, click, type, screenshot, close, list）都能正常工作
- [ ] 支持多个浏览器实例同时运行
- [ ] 每个操作（除 list 和 close）后都能自动保存页面内容
- [ ] 返回值中包含正确的 `output_files` 列表

### 2. 内容保存

- [ ] HTML 模式能正确保存完整 HTML
- [ ] 抽象模式能正确提取可交互控件
- [ ] 抽象模式输出格式正确，易于搜索
- [ ] 文件名包含时间戳和操作类型
- [ ] 文件路径正确返回

### 3. 等待条件

- [ ] network_idle 模式能正确等待网络请求完成
- [ ] timeout 模式能正确等待指定时间
- [ ] 超时保护机制有效

### 4. 错误处理

- [ ] 浏览器未启动时操作返回错误
- [ ] 元素不存在时返回清晰的错误信息
- [ ] URL 无效时返回错误信息
- [ ] Playwright 未安装时返回安装提示

### 5. 资源管理

- [ ] close 操作能正确关闭浏览器
- [ ] close 操作能正确释放资源
- [ ] 重复关闭不会报错
- [ ] launch 重复创建会先关闭旧会话

### 6. 代码质量

- [ ] 代码符合项目编码规范
- [ ] 有适当的注释
- [ ] 错误处理完善
- [ ] 类型注解正确

### 7. 集成测试

- [ ] 工具能被正确注册到工具注册表
- [ ] Agent 能正确调用工具
- [ ] 返回值格式符合预期

## 依赖要求

### 必需依赖

```bash
pip install playwright
playwright install chromium
```

### 可选依赖

- 无

## 实现建议

### 参考实现

- 参考 `src/jarvis/jarvis_tools/virtual_tty.py` 的实现模式
- 保持相似的类结构和参数定义风格

### 关键设计点

1. **会话管理**：使用 `agent.browser_sessions` 字典存储浏览器实例
2. **自动保存**：每个操作后调用 `_save_page_content` 方法
3. **平台兼容**：Playwright 本身跨平台，无需特殊处理
4. **错误处理**：捕获所有异常，返回友好的错误信息

### 代码结构

```python
class PlaywrightBrowserTool:
    def execute(self, args):
        # 主入口，分发到各个操作方法
        pass

    def _launch_browser(self):
        # 启动浏览器
        pass

    def _navigate(self):
        # 导航到 URL
        pass

    def _click(self):
        # 点击元素
        pass

    def _type(self):
        # 输入文本
        pass

    def _screenshot(self):
        # 截图
        pass

    def _close_browser(self):
        # 关闭浏览器
        pass

    def _list_browsers(self):
        # 列出浏览器
        pass

    def _save_page_content(self):
        # 保存页面内容
        pass

    def _extract_interactive_elements(self):
        # 提取可交互元素
        pass

    def _wait_for_condition(self):
        # 等待条件
        pass
```

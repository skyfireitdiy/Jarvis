---
description: Jarvis Browser CLI使用指南，浏览器自动化命令行工具，支持35+命令和守护进程模式
---

# Jarvis Browser CLI (jb) 使用指南

## 概述

`jb` (或 `jarvis-browser`) 是一个基于 Playwright 的浏览器自动化命令行工具，支持守护进程模式，可以跨多个 CLI 调用维护浏览器会话。

## 快速开始

```bash
# 1. 启动守护进程（后台运行）
jb daemon

# 2. 启动浏览器
jb launch --browser-id demo

# 3. 导航到页面
jb navigate --url https://example.com --browser-id demo

# 4. 获取页面文本
jb gettext --selector 'h1' --browser-id demo

# 5. 截图
jb screenshot --browser-id demo --path /tmp/screenshot.png
```

## 通用参数

所有命令都支持以下可选参数：

- `--browser-id TEXT`: 浏览器会话 ID（默认：`default`）

## 命令列表

### 1. 守护进程管理

#### daemon - 启动守护进程

启动后台守护进程，用于持久化浏览器会话。守护进程会脱离终端持续运行，即使终端关闭也不会退出。

**参数：**

无（socket 固定为 `~/.jarvis/playwright_daemon.sock`）

**示例：**

```bash
jb daemon
jb daemon-stop   # 关闭守护进程
```

**说明：**

- 守护进程会检查是否已运行，如果已运行则不会重复启动
- 使用 double-fork 方法实现真正的后台守护进程
- 若 30 分钟内无任何请求，守护进程将自动退出以节省资源
- 运行日志写入 `~/.jarvis/logs/browser_daemon/daemon.log`，包含各类浏览器操作记录（如 launch、navigate、click 等）

#### daemon-stop - 关闭守护进程

优雅关闭守护进程，所有浏览器会话将被关闭。

**参数：** 无

**示例：**

```bash
jb daemon-stop
```

### 2. 浏览器管理

#### launch - 启动浏览器

启动一个新的浏览器实例。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**说明：**

- 优先尝试有界面（UI）模式启动；若失败则自动回退为无头（headless）模式。

**示例：**

```bash
jb launch --browser-id demo
```

#### close - 关闭浏览器

关闭指定的浏览器实例。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb close --browser-id demo
```

#### list - 列出浏览器

列出所有活动的浏览器会话。

**参数：**

无

**示例：**

```bash
jb list
```

### 3. 页面导航

#### navigate - 导航到 URL

将浏览器导航到指定的 URL。

**参数：**

- `-u, --url TEXT`: 要导航的 URL（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb navigate --url https://example.com --browser-id demo
```

#### goback - 后退

导航到上一页。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb goback --browser-id demo
```

#### goforward - 前进

导航到下一页。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb goforward --browser-id demo
```

### 4. 元素交互

#### click - 点击元素

点击元素。支持 CSS 选择器或 list-interactables 的编号。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（与 --index 二选一）
- `-i, --index INT`: 可交互元素编号（与 --selector 二选一）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb click --selector '#submit-button' --browser-id demo
jb click --index 3 --browser-id demo   # 点击 list-interactables 中的第 3 个元素
```

#### type - 输入文本

在元素中输入文本。支持 CSS 选择器或 list-interactables 的编号。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（与 --index 二选一）
- `-i, --index INT`: 可交互元素编号（与 --selector 二选一）
- `-t, --text TEXT`: 要输入的文本（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb type --selector '#username' --text 'myuser' --browser-id demo
jb type --index 5 --text 'user@example.com' --browser-id demo
```

#### hover - 悬停

将鼠标移动到匹配的元素上。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb hover --selector '.menu-item' --browser-id demo
```

#### drag - 拖拽

将源元素拖拽到目标元素。

**参数：**

- `-s, --selector TEXT`: 源元素的 CSS 选择器（必需）
- `-t, --target-selector TEXT`: 目标元素的 CSS 选择器（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb drag --selector '#draggable' --target-selector '#dropzone' --browser-id demo
```

#### doubleclick - 双击

双击匹配的元素。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb doubleclick --selector '.file' --browser-id demo
```

#### presskey - 按键

按指定的键盘键。

**参数：**

- `-k, --key TEXT`: 要按的键（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb presskey --key 'Enter' --browser-id demo
jb presskey --key 'Escape' --browser-id demo
```

### 5. 信息获取

#### screenshot - 页面截图

截取当前页面的屏幕截图。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `-p, --path TEXT`: 截图路径（默认：`/tmp/screenshot.png`）

**示例：**

```bash
jb screenshot --browser-id demo --path /tmp/my_screenshot.png
```

#### gettext - 获取文本

从匹配的元素获取文本内容。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb gettext --selector 'h1' --browser-id demo
jb gettext --selector '.title' --browser-id demo
```

#### getattribute - 获取属性

从选定元素获取属性值。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（必需）
- `-a, --attribute TEXT`: 属性名（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb getattribute --selector '#link' --attribute 'href' --browser-id demo
jb getattribute --selector 'img' --attribute 'src' --browser-id demo
```

#### getelementinfo - 获取元素信息

获取选定元素的详细信息。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb getelementinfo --selector '#main-content' --browser-id demo
```

#### get-markdown - 获取页面 Markdown

将当前页面的 HTML 内容转换为 Markdown 格式。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb get-markdown --browser-id demo
```

**说明：**

- 使用 markdownify 库将页面 HTML 转换为 Markdown
- 适用于提取页面结构化内容
- 返回的 Markdown 格式可直接用于文档生成或内容分析

#### list-interactables - 列出交互控件

列出页面上所有可交互的元素（按钮、输入框、链接等）。返回的 `selector` 与 click、type 等命令一致，可直接用于后续操作。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `-f, --filter TEXT`: 按元素类型过滤（可选：`button`, `input`, `link`, `checkbox`, `radio`, `select`, `file`）

**示例：**

```bash
# 列出所有交互控件
jb list-interactables --browser-id demo

# 只列出按钮
jb list-interactables --browser-id demo --filter button

# 只列出输入框
jb list-interactables --browser-id demo --filter input

# 只列出链接
jb list-interactables --browser-id demo --filter link
```

**说明：**

- 支持的元素类型包括：
  - `button`: 按钮、提交按钮、重置按钮等
  - `input`: 文本输入框、密码框、邮箱框、数字输入框、文本区域
  - `link`: 带有 href 属性的链接
  - `checkbox`: 复选框
  - `radio`: 单选按钮
  - `select`: 下拉选择框
  - `file`: 文件上传输入框
- 每个元素返回的信息包括：编号（index）、类型、选择器、文本内容
- click、type、gettext、hover、doubleclick、getelementinfo、getattribute、elementscreenshot 支持 `--index` 参数，可直接用编号操作
- **selector 生成优先级**：`#id` > `[name]` > `[placeholder]` > `[aria-label]` > `[data-testid]` > `a[href]` > `.class:nth-of-type(n)` > `tag:nth-of-type(n)`，尽量保证唯一性
- 最多返回 100 个元素，避免数据量过大
- 元素文本内容限制为 100 个字符

#### elementscreenshot - 元素截图

截取指定元素的屏幕截图。

**参数：**

- `-s, --selector TEXT`: 元素的 CSS 选择器（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb elementscreenshot --selector '.header' --browser-id demo --path /tmp/element.png
```

#### console - 获取控制台日志

从浏览器会话获取控制台日志。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `--clear-logs`: 读取后清除日志

**示例：**

```bash
jb console --browser-id demo
jb console --browser-id demo --clear-logs
```

#### eval - 执行 JavaScript

在浏览器上下文中执行 JavaScript 代码。

**参数：**

- `-c, --code TEXT`: 要执行的 JavaScript 代码（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `--save-result`: 将结果保存到文件

**示例：**

```bash
jb eval --code 'document.title' --browser-id demo
jb eval --code 'window.scrollY' --browser-id demo
jb eval --code 'document.querySelectorAll("a").length' --browser-id demo
```

#### getperformancemetrics - 获取性能指标

获取当前页面的性能指标。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb getperformancemetrics --browser-id demo
```

### 6. 等待操作

#### waitforselector - 等待选择器

等待元素达到指定状态。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `--wait-state TEXT`: 等待状态（visible, hidden, attached, detached）（默认：`visible`）
- `-t, --timeout FLOAT`: 超时时间（秒）（默认：30.0）

**示例：**

```bash
jb waitforselector --selector '#content' --browser-id demo
jb waitforselector --selector '.loading' --wait-state hidden --browser-id demo
jb waitforselector --selector '#button' --timeout 10 --browser-id demo
```

#### waitfortext - 等待文本

等待文本出现在页面上。

**参数：**

- `-t, --text TEXT`: 要等待的文本（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `-s, --selector TEXT`: CSS 选择器（默认：`*`）
- `--timeout FLOAT`: 超时时间（秒）（默认：30.0）

**示例：**

```bash
jb waitfortext --text 'Loading complete' --browser-id demo
jb waitfortext --text 'Success' --selector '#status' --browser-id demo
```

### 7. 表单操作

#### fillform - 填写表单

用值填充多个表单字段。

**参数：**

- `-f, --fields TEXT`: 表单字段（JSON 字符串格式）（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb fillform --fields '{"#username":"john","#password":"secret","#email":"john@example.com"}' --browser-id demo
```

#### submitform - 提交表单

提交指定的表单。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `--form-selector TEXT`: 表单选择器（默认：`form`）

**示例：**

```bash
jb submitform --browser-id demo
jb submitform --form-selector '#login-form' --browser-id demo
```

#### clearform - 清除表单

清除指定表单中的所有字段。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `--form-selector TEXT`: 表单选择器（默认：`form`）

**示例：**

```bash
jb clearform --browser-id demo
jb clearform --form-selector '#contact-form' --browser-id demo
```

### 8. 文件操作

#### uploadfile - 上传文件

上传文件到指定的输入元素。

**参数：**

- `-s, --selector TEXT`: CSS 选择器（必需）
- `-f, --file-path TEXT`: 要上传的文件路径（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb uploadfile --selector '#file-input' --file-path /tmp/document.pdf --browser-id demo
```

#### downloadfile - 下载文件

从当前页面下载文件。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）
- `-s, --selector TEXT`: 下载按钮/链接的 CSS 选择器

**示例：**

```bash
jb downloadfile --browser-id demo
jb downloadfile --selector '#download-btn' --browser-id demo
```

### 9. 标签页管理

#### newtab - 创建新标签页

在浏览器中创建新标签页。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb newtab --browser-id demo
```

#### switchtab - 切换标签页

切换到指定的标签页。

**参数：**

- `-p, --page-id TEXT`: 要切换到的页面 ID（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb switchtab --page-id 2 --browser-id demo
```

#### closetab - 关闭标签页

关闭指定的标签页。

**参数：**

- `-p, --page-id TEXT`: 要关闭的页面 ID（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb closetab --page-id 1 --browser-id demo
```

### 10. 滚动操作

#### scrollto - 滚动到位置

滚动到页面上的指定位置。

**参数：**

- `-x, --scroll-x INTEGER`: 滚动到的 X 坐标（默认：0）
- `-y, --scroll-y INTEGER`: 滚动到的 Y 坐标（默认：0）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb scrollto --scroll-x 0 --scroll-y 500 --browser-id demo
```

#### scrolldown - 向下滚动

向下滚动页面指定数量。

**参数：**

- `-a, --scroll-amount INTEGER`: 向下滚动的像素数（默认：300）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb scrolldown --scroll-amount 500 --browser-id demo
jb scrolldown --browser-id demo  # 使用默认值
```

#### scrollup - 向上滚动

向上滚动页面指定数量。

**参数：**

- `-a, --scroll-amount INTEGER`: 向上滚动的像素数（默认：300）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb scrollup --scroll-amount 500 --browser-id demo
```

### 11. Cookie 管理

#### getcookies - 获取 Cookie

获取浏览器的所有 Cookie。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb getcookies --browser-id demo
```

#### setcookies - 设置 Cookie

从 JSON 字符串设置 Cookie。

**参数：**

- `-c, --cookies TEXT`: Cookie（JSON 列表格式）（必需）
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb setcookies --cookies '[{"name":"session","value":"abc123","domain":"example.com"}]' --browser-id demo
```

#### clearcookies - 清除 Cookie

清除浏览器的所有 Cookie。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb clearcookies --browser-id demo
```

### 12. LocalStorage 管理

#### getlocalstorage - 获取 LocalStorage

获取页面的所有 LocalStorage 数据。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb getlocalstorage --browser-id demo
```

#### setlocalstorage - 设置 LocalStorage

从 JSON 字符串设置 LocalStorage。

**参数：**

- `-d, --data TEXT`: 存储数据（JSON 字典格式）（必需）
- `--clear`: 设置前清除所有 LocalStorage
- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb setlocalstorage --data '{"user":"john","token":"abc123"}' --browser-id demo
jb setlocalstorage --data '{"key":"value"}' --clear --browser-id demo
```

### 13. 网络监控

#### startnetworkmonitor - 启动网络监控

开始监控网络请求。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb startnetworkmonitor --browser-id demo
```

#### getnetworkrequests - 获取网络请求

获取所有记录的网络请求。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb getnetworkrequests --browser-id demo
```

### 14. PDF 导出

#### exportpdf - 导出 PDF

将当前页面导出为 PDF。

**参数：**

- `--browser-id TEXT`: 浏览器 ID（默认：`default`）

**示例：**

```bash
jb exportpdf --browser-id demo
```

## 完整使用示例

### 网页自动化示例

```bash
# 1. 启动守护进程
jb daemon

# 2. 启动浏览器
jb launch --browser-id mybrowser

# 3. 导航到登录页面
jb navigate --url https://example.com/login --browser-id mybrowser

# 4. 填写登录表单
jb fillform --fields '{"#username":"myuser","#password":"mypass"}' --browser-id mybrowser

# 5. 提交表单
jb submitform --browser-id mybrowser

# 6. 等待登录成功
jb waitfortext --text "Welcome" --browser-id mybrowser

# 7. 截图
jb screenshot --path /tmp/after_login.png --browser-id mybrowser

# 8. 关闭浏览器
jb close --browser-id mybrowser
```

### 数据抓取示例

```bash
# 1. 启动守护进程和浏览器
jb daemon
jb launch --browser-id scraper

# 2. 导航到目标页面
jb navigate --url https://example.com/articles --browser-id scraper

# 3. 等待内容加载
jb waitforselector --selector '.article-list' --browser-id scraper

# 4. 获取所有文章标题
jb eval --code 'Array.from(document.querySelectorAll(".article-title")).map(el => el.textContent)' --browser-id scraper

# 5. 截图
jb screenshot --path /tmp/articles.png --browser-id scraper
# 6. 导出 PDF
jb exportpdf --browser-id scraper
```

### 表单测试示例

```bash
# 1. 启动守护进程和浏览器
jb daemon
jb launch --browser-id form_test

# 2. 导航到表单页面
jb navigate --url https://example.com/contact --browser-id form_test

# 3. 填写表单
jb type --selector '#name' --text 'John Doe' --browser-id form_test
jb type --selector '#email' --text 'john@example.com' --browser-id form_test
jb type --selector '#message' --text 'Hello, this is a test message.' --browser-id form_test

# 4. 截图
jb screenshot --path /tmp/filled_form.png --browser-id form_test

# 5. 提交表单
jb click --selector '#submit' --browser-id form_test

# 6. 等待确认
jb waitforselector --selector '.success-message' --browser-id form_test

# 7. 获取成功消息
jb gettext --selector '.success-message' --browser-id form_test
```

## 最佳实践

### 1. 始终使用浏览器 ID

为不同的任务使用不同的浏览器 ID，避免冲突：

```bash
jb launch --browser-id task1
jb launch --browser-id task2
```

### 2. 使用等待而不是睡眠

不要使用固定的等待时间，而是使用 `waitforselector` 或 `waitfortext`：

```bash
# 不推荐
sleep 5
jb click --selector '#button' --browser-id demo

# 推荐
jb waitforselector --selector '#button' --browser-id demo
jb click --selector '#button' --browser-id demo
```

### 3. 使用 CSS 选择器

优先使用稳定的 CSS 选择器，避免脆弱的选择器：

```bash
# 脆弱（依赖于位置）
jb click --selector 'div:nth-child(3)' --browser-id demo

# 稳定（基于语义）
jb click --selector '#submit-button' --browser-id demo
```

### 4. 错误处理

所有命令返回 JSON 格式的响应：

```json
{
  "success": true,
  "stdout": "操作输出",
  "stderr": "错误信息"
}
```

### 5. 调试技巧

使用 `getelementinfo` 和 `console` 来调试：

```bash
# 检查元素状态
jb getelementinfo --selector '#element' --browser-id demo

# 检查控制台日志
jb console --browser-id demo

# 执行调试 JavaScript
jb eval --code 'console.log("debug"); document.title' --browser-id demo
```

### 6. 性能优化

对于大型页面，考虑使用无头模式：

```bash
jb launch --browser-id demo
```

### 7. 会话管理

定期检查活动会话：

```bash
jb list
```

完成工作后关闭浏览器：

```bash
jb close --browser-id demo
```

## 故障排除

### 守护进程未运行

**错误：** `Daemon not running at ~/.jarvis/playwright_daemon.sock`

**解决：**

```bash
# 检查守护进程是否运行
ps aux | grep 'jb daemon'

# 重新启动守护进程
jb daemon
```

### Socket 文件冲突

**错误：** `Address already in use`

**解决：**

```bash
# 清理旧的 socket 文件
rm -f ~/.jarvis/playwright_daemon.sock

# 重新启动守护进程
jb daemon
```

### 元素未找到

**错误：** `Element not found`

**解决：**

```bash
# 1. 等待元素出现
jb waitforselector --selector '#element' --browser-id demo

# 2. 检查选择器是否正确
jb getelementinfo --selector '#element' --browser-id demo
# 3. 检查页面源代码
jb eval --code 'document.body.innerHTML' --browser-id demo
```

### 超时错误

**错误：** `Timeout waiting for element`

**解决：**

```bash
# 增加超时时间
jb waitforselector --selector '#element' --timeout 60 --browser-id demo

# 或者等待不同的状态
jb waitforselector --selector '#loading' --wait-state hidden --browser-id demo
```

## 命令速查表

| 命令                  | 描述              | 关键参数                                                  |
| --------------------- | ----------------- | --------------------------------------------------------- |
| daemon                | 启动守护进程      | 无                                                        |
| daemon-stop           | 关闭守护进程      | 无                                                        |
| launch                | 启动浏览器        | --browser-id                                             |
| close                 | 关闭浏览器        | --browser-id                                              |
| list                  | 列出浏览器        | 无                                                        |
| navigate              | 导航到 URL        | --url (必需), --browser-id                                |
| click                 | 点击元素          | --selector (必需), --browser-id                           |
| type                  | 输入文本          | --selector (必需), --text (必需), --browser-id            |
| screenshot            | 页面截图          | --path, --browser-id                                      |
| gettext               | 获取文本          | --selector (必需), --browser-id                           |
| getelementinfo        | 元素信息          | --selector (必需), --browser-id                           |
| getattribute          | 获取属性          | --selector (必需), --attribute (必需), --browser-id       |
| waitforselector       | 等待选择器        | --selector (必需), --wait-state, --timeout, --browser-id  |
| waitfortext           | 等待文本          | --text (必需), --selector, --timeout, --browser-id        |
| hover                 | 悬停              | --selector (必需), --browser-id                           |
| drag                  | 拖拽              | --selector (必需), --target-selector (必需), --browser-id |
| doubleclick           | 双击              | --selector (必需), --browser-id                           |
| presskey              | 按键              | --key (必需), --browser-id                                |
| fillform              | 填写表单          | --fields (必需), --browser-id                             |
| submitform            | 提交表单          | --form-selector, --browser-id                             |
| clearform             | 清除表单          | --form-selector, --browser-id                             |
| uploadfile            | 上传文件          | --selector (必需), --file-path (必需), --browser-id       |
| downloadfile          | 下载文件          | --selector, --browser-id                                  |
| newtab                | 新标签页          | --browser-id                                              |
| switchtab             | 切换标签页        | --page-id (必需), --browser-id                            |
| closetab              | 关闭标签页        | --page-id (必需), --browser-id                            |
| goback                | 后退              | --browser-id                                              |
| goforward             | 前进              | --browser-id                                              |
| scrollto              | 滚动到位置        | --scroll-x, --scroll-y, --browser-id                      |
| scrolldown            | 向下滚动          | --scroll-amount, --browser-id                             |
| scrollup              | 向上滚动          | --scroll-amount, --browser-id                             |
| getcookies            | 获取 Cookie       | --browser-id                                              |
| setcookies            | 设置 Cookie       | --cookies (必需), --browser-id                            |
| clearcookies          | 清除 Cookie       | --browser-id                                              |
| getlocalstorage       | 获取 LocalStorage | --browser-id                                              |
| setlocalstorage       | 设置 LocalStorage | --data (必需), --clear, --browser-id                      |
| startnetworkmonitor   | 启动网络监控      | --browser-id                                              |
| getnetworkrequests    | 获取网络请求      | --browser-id                                              |
| elementscreenshot     | 元素截图          | --selector (必需), --browser-id                           |
| exportpdf             | 导出 PDF          | --browser-id                                              |
| console               | 获取控制台日志    | --browser-id, --clear-logs                                |
| eval                  | 执行 JavaScript   | --code (必需), --save-result, --browser-id                |
| getperformancemetrics | 性能指标          | --browser-id                                              |

## 相关文档

- [Playwright 文档](https://playwright.dev/python/)
- [CSS 选择器参考](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Selectors)
- [Typer 文档](https://typer.tiangolo.com/)

## 版本信息

- 工具名称: Jarvis Browser CLI
- 命令: jb, jarvis-browser
- 守护进程: 支持后台持续运行
- 输出格式: JSON

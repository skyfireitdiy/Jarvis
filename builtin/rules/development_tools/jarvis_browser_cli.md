|
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

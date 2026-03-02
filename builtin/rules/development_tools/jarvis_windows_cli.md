|
| start                 | 启动应用     | --path (必需), --args                |
| connect               | 连接窗口     | --process / --title / --pid 至少其一 |
| list                  | 列出会话     | --app-id                             |
| list-windows          | 列举可见窗口 | --title 过滤, --limit                |
| close                 | 关闭会话     | --app-id, --kill/--no-kill           |
| click                 | 点击         | --control, --menu, --index           |
| double-click          | 双击         | --control (必需), --index            |
| right-click           | 右键点击     | --control                            |
| hover                 | 移动鼠标     | --control 或 --x --y                 |
| drag                  | 拖拽         | --from-control, --to-control 或坐标  |
| type                  | 输入文本     | --text (必需), --control             |
| type-keys             | 发送按键     | --keys (必需)                        |
| screenshot            | 截图         | --path                               |
| get-tree              | 获取控件树   | --depth (默认99), --control          |
| menu                  | 执行菜单     | --path (必需)                        |
| config theme          | 主题切换     | dark / light / toggle                |
| config power-plan     | 电源计划     | list / set --id                      |
| config proxy          | 系统代理     | get / enable / disable / set         |
| config screen-timeout | 熄屏超时     | get / set --minutes                  |
| config remote-desktop | 远程桌面     | enable / disable / get               |
| config startup        | 启动项       | list / enable / disable --name       |

## 相关文档

- [pywinauto 文档](https://pywinauto.readthedocs.io/)
- [Windows App 工具规范]({{ git_root_dir }}/.jarvis/spec/windows_app_tool_spec.md)

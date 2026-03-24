# 分析外部安全问题 JSON

## 使用场景

当你已经有一份外部生成的安全问题 JSON 文件，想让 Jarvis 对这些问题做进一步归类、聚合和分析时，可以直接使用外部 JSON 分析入口，而不必重新扫描代码。

## 操作步骤

1. 准备一份安全问题 JSON 文件。
2. 在终端中输入基础命令：`jsec analyze 你的问题.json`
3. 如需保存 Markdown 报告并限制单批处理数量，可运行：`jsec analyze 你的问题.json --output-format markdown --output-file report.md --cluster-limit 30 --enable-verification`
4. 如果你希望关闭二次验证或关闭强制记忆，也可以显式指定：`jsec analyze 你的问题.json --no-verification --no-force-save-memory`
5. 提交命令后，等待系统读取并分析输入文件中的问题列表。
6. 如需保存结果，可以指定输出文件；如果不指定，结果会直接显示在终端中。

## 你会看到的提示与反馈

- 分析成功时，系统会输出分析结果，或者把报告写入指定文件。
- 如果输入 JSON 不符合标准格式，系统会尽量做兼容转换后继续分析。
- 如果输入文件不存在，系统会明确提示错误并退出。
- 如果分析失败或发生未知错误，系统会给出明确失败提示。
- 默认情况下，二次验证会处于启用状态；如不需要，可用 `--no-verification` 显式关闭。

## 注意事项

- 这是对“已有问题列表”的分析，不是重新扫描源代码。
- 如果未指定输出文件，结果会直接打印在终端里。
- 输入文件需要是可读取的 JSON 文件，否则流程无法开始。
- `--enable-verification/--no-verification` 与 `--force-save-memory/--no-force-save-memory` 是成对布尔开关，按需显式选择即可。
- 如果你想按当前项目配置直接扫描代码，应使用“执行安全扫描”入口，而不是这个命令。

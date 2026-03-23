# 配置额外的 Agent 定义目录

## 使用场景

如果你希望 Jarvis 在默认 Agent 定义之外，还能识别你自己维护的 Agent 定义文件，可以通过 `agent_definition_dirs` 增加额外搜索目录。

## 操作步骤

1. 准备好一个或多个 Agent 定义目录。
2. 把你希望被识别的 Agent 定义文件放入这些目录。
3. 打开 Jarvis 全局配置文件：`~/.jarvis/config.yaml`。
4. 添加或修改 `agent_definition_dirs`。例如：

   ```yaml
   agent_definition_dirs:
     - ~/jarvis-agents
     - /opt/team/jarvis-agents
   ```

5. 保存配置文件。
6. 重新启动相关会话或相关入口。
7. 之后系统在发现 Agent 定义时，会把这些目录一起纳入搜索范围。

## 你会看到的提示与反馈

- 配置生效后，你原本看不到的自定义 Agent，可能会出现在后续可选 Agent 来源中。
- 如果目录路径无效，或者目录中的定义文件不符合要求，你不会看到预期的新增 Agent。
- 更直接的验证方法，是在启动选择或 Agent 相关入口中确认新增定义是否出现。

## 注意事项

- 配置项名称是 `agent_definition_dirs`。
- 这是扩展搜索目录，不是替代默认 Agent 定义来源。
- 目录里只应放你希望系统扫描的 Agent 定义内容，避免混入无关文件。
- 改完后建议重新启动对应入口，确认新目录确实已被纳入扫描。

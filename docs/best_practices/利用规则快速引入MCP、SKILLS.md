# 利用规则快速引入 MCP、SKILLS

## 1. 概述

### 1.1 什么是 MCP 和 SKILLS

- **MCP (Model Context Protocol)**：模型上下文协议，允许 Jarvis 通过标准协议与外部独立进程通信，接入该进程提供的工具和资源。
- **SKILLS**：Jarvis 的技能系统，允许通过 Git 仓库或本地路径添加可复用的技能模块。

### 1.2 为什么使用规则引入

Jarvis 提供了专门的规则来指导 MCP 和 SKILLS 的集成：

- **`mcp-integration.md`**：MCP 集成规则，指导如何配置和集成 MCP 工具
- **`skill-development.md`**：技能开发规则，指导如何添加和管理技能

使用这些规则可以让 Agent 自动完成集成工作，减少手动配置错误，提高效率。

---

## 2. 快速引入 MCP

### 2.1 使用规则引入 MCP

最简单的方式是直接使用规则，让 Agent 帮你完成 MCP 集成：

```bash
# 方式 1：在命令行中使用规则
jca --rule-names mcp-integration "集成 filesystem MCP 服务器，路径为 /home/user/documents"

# 方式 2：在交互式会话中使用规则
jca
> '<rule:mcp-integration>' 集成 filesystem MCP 服务器，路径为 /home/user/documents
```

### 2.2 MCP 集成流程

Agent 会根据规则自动执行以下步骤：

1. **配置准备阶段**
   - 确定 MCP 服务器类型和通信方式
   - 准备 MCP 服务器运行环境和依赖
   - 规划客户端命名和配置结构

2. **配置编写阶段**
   - 在 `~/.jarvis/config.yaml` 文件中添加 MCP 配置
   - 根据服务器类型选择正确的客户端配置格式
   - 验证 YAML 语法和配置完整性

3. **验证测试阶段**
   - 重启 Jarvis 加载新配置
   - 检查启动日志确认配置加载成功
   - 验证 MCP 工具是否正确注册和可用

### 2.3 MCP 集成示例

#### 示例 1：集成 stdio 类型的 MCP 服务器

```bash
jca --rule-names mcp-integration "
集成 filesystem MCP 服务器：
- 类型：stdio
- 命令：npx -y @modelcontextprotocol/server-filesystem
- 参数：/home/user/documents
- 名称：filesystem
"
```

Agent 会自动生成配置：

```yaml
# ~/.jarvis/config.yaml
mcp:
  - type: "stdio"
    name: "filesystem"
    command: "npx"
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/home/user/documents"
```

#### 示例 2：集成 SSE 类型的 MCP 服务器

```bash
jca --rule-names mcp-integration "
集成远程 MCP 服务器：
- 类型：sse
- URL：https://api.example.com/mcp
- 名称：remote-tools
"
```

Agent 会自动生成配置：

```yaml
# ~/.jarvis/config.yaml
mcp:
  - type: "sse"
    name: "remote-tools"
    base_url: "https://api.example.com/mcp"
```

#### 示例 3：集成多个 MCP 客户端

```bash
jca --rule-names mcp-integration "
集成多个 MCP 服务器：
1. filesystem：stdio 类型，路径 /home/user/documents
2. database：stdio 类型，命令 python -m mcp_database_server
3. remote-api：sse 类型，URL https://api.example.com/mcp
"
```

### 2.4 验证 MCP 集成

集成完成后，Agent 会自动验证：

```bash
# Agent 会自动执行验证步骤
1. 检查配置文件格式
2. 验证 MCP 服务器可访问性
3. 测试工具注册情况
4. 提供验证报告
```

如果验证失败，Agent 会提供详细的错误信息和修复建议。

---

## 3. 快速引入 SKILLS

### 3.1 使用规则引入 SKILLS

使用技能开发规则，让 Agent 帮你添加技能：

```bash
# 方式 1：从 Git 仓库添加技能
jca --rule-names skill-development "添加技能：https://github.com/user/skill-repo.git"

# 方式 2：从本地路径添加技能
jca --rule-names skill-development "添加技能：/path/to/local/skill"

# 方式 3：在交互式会话中使用规则
jca
> '<rule:skill-development>' 添加技能：https://github.com/user/skill-repo.git
```

### 3.2 SKILLS 添加流程

Agent 会根据规则自动执行以下步骤：

1. **输入处理与验证**
   - 接收用户输入（本地路径或 Git URL）
   - 判断输入类型（Git URL 或本地路径）
   - 验证路径或 URL 的有效性

2. **Git 仓库处理**（如果是 Git URL）
   - 检查技能目录是否存在
   - 提取仓库名称
   - 执行克隆操作
   - 处理克隆失败情况

3. **本地路径验证**（如果是本地路径）
   - 路径存在性检查
   - 路径可读性验证
   - 错误处理

4. **技能功能分析**
   - 读取关键文档（README、package.json、setup.py 等）
   - 提取技能名称、功能描述、主要特性
   - 评估复杂度（简单技能直接读取，复杂技能使用 task_list_manager）

5. **技能信息注册**
   - 在 `~/.jarvis/rule` 中注册技能信息
   - 使用统一格式记录技能名称、功能描述、位置、添加时间

### 3.3 SKILLS 添加示例

#### 示例 1：从 Git 仓库添加技能

```bash
jca --rule-names skill-development "
添加技能：
- Git URL：https://github.com/user/my-skill.git
- 功能：这是一个用于处理数据的技能模块
"
```

Agent 会自动执行：

```bash
1. 克隆仓库到 ~/.jarvis/skills/my-skill
2. 分析技能功能（读取 README.md）
3. 在 ~/.jarvis/rule 中注册技能信息
```

#### 示例 2：从本地路径添加技能

```bash
jca --rule-names skill-development "
添加技能：
- 本地路径：/home/user/my-local-skill
- 功能：本地开发的技能模块
"
```

Agent 会自动执行：

```bash
1. 验证路径存在性和可读性
2. 分析技能功能
3. 在 ~/.jarvis/rule 中注册技能信息
```

#### 示例 3：批量添加技能

```bash
jca --rule-names skill-development "
批量添加技能：
1. https://github.com/user/skill1.git
2. https://github.com/user/skill2.git
3. /path/to/local/skill3
"
```

### 3.4 技能信息注册格式

Agent 会自动在 `~/.jarvis/rule` 中注册技能信息：

```markdown
## [技能名称]

- **功能描述**：[技能的核心功能描述]
- **位置**：[技能的完整路径]
- **添加时间**：[YYYY-MM-DD HH:MM:SS]
```

---

## 4. 高级用法

### 4.1 组合使用规则

可以同时使用多个规则来完成复杂的集成任务：

```bash
jca --rule-names mcp-integration,skill-development "
任务：完整集成开发环境

1. 集成 MCP：
   - filesystem MCP：路径 /home/user/projects
   - database MCP：命令 python -m mcp_database_server

2. 添加技能：
   - https://github.com/user/code-analysis-skill.git
   - https://github.com/user/test-generation-skill.git
"
```

### 4.2 自定义配置

如果需要自定义配置，可以在任务描述中详细说明：

```bash
jca --rule-names mcp-integration "
集成自定义 MCP 服务器：
- 类型：stdio
- 命令：/usr/local/bin/my-mcp-server
- 参数：--config /path/to/config.json
- 环境变量：
  - API_KEY: your-api-key
  - DEBUG: true
- 名称：my-custom-mcp
"
```

### 4.3 错误处理和重试

如果集成过程中出现错误，Agent 会：

1. **提供详细的错误信息**
2. **给出修复建议**
3. **支持重试机制**

例如：

```bash
# 如果 Git 克隆失败
Agent: ⚠️ Git 克隆失败，可能的原因：
1. 网络连接问题
2. URL 格式错误
3. 仓库不存在或无权访问

请选择：
1. 重试
2. 更换 URL
3. 放弃
```

---

## 5. 最佳实践

### 5.1 MCP 集成最佳实践

1. **明确指定类型**：在任务描述中明确指定 MCP 服务器类型（stdio、sse、streamable）
2. **使用有意义的名称**：为 MCP 客户端使用有意义的名称，便于识别
3. **验证配置**：集成完成后验证配置是否正确
4. **文档记录**：记录每个 MCP 的用途和配置

### 5.2 SKILLS 添加最佳实践

1. **使用版本控制**：优先使用 Git 仓库而非本地路径
2. **清晰的功能描述**：在任务描述中提供清晰的功能说明
3. **及时更新**：定期更新技能到最新版本
4. **文档维护**：保持技能文档的更新

### 5.3 规则使用最佳实践

1. **明确任务描述**：提供清晰、详细的任务描述
2. **使用规则名称**：使用正确的规则名称（`mcp-integration`、`skill-development`）
3. **验证结果**：集成完成后验证功能是否正常
4. **错误处理**：遇到错误时查看 Agent 提供的详细错误信息

---

## 6. 实际应用场景

### 场景 1：快速集成开发工具链

```bash
jca --rule-names mcp-integration,skill-development "
集成完整的开发工具链：

MCP 集成：
1. filesystem：访问项目文件
2. git：Git 操作工具
3. database：数据库操作工具

技能添加：
1. code-analysis：代码分析技能
2. test-generation：测试生成技能
3. documentation：文档生成技能
"
```

### 场景 2：团队协作环境搭建

```bash
jca --rule-names mcp-integration "
为团队配置统一的 MCP 环境：
- 共享的 filesystem MCP：路径 /shared/projects
- 团队数据库 MCP：连接团队数据库
- 代码审查 MCP：集成代码审查工具
"
```

### 场景 3：项目特定技能集成

```bash
jca --rule-names skill-development "
为当前项目添加专用技能：
- 项目技能仓库：https://github.com/company/project-skills.git
- 本地开发技能：./local-skills
"
```

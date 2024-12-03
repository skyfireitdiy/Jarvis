# jcad 最佳实践

## 1. 概述

### 1.1 什么是 jcad

`jcad`（Jarvis Code Agent Dispatcher）是 Jarvis 代码代理（`jca`）的
便捷派发工具，旨在简化代码任务的快速启动和管理。它是
`jarvis-code-agent-dispatcher` 命令的快捷别名。

### 1.2 核心特性

- **自动化模式启用**：自动启用非交互模式（`-n`）、工作树模式（`--worktree`）和任务派发（`--dispatch`）
- **多行任务支持**：支持多行任务输入，自动创建临时文件处理
- **Git 隔离开发**：默认启用 Git worktree，确保在独立分支上开发
- **交互式输入**：提供友好的多行输入界面（Ctrl+J/Ctrl+] 确认）
- **Tmux 集成**：智能调度任务到独立的 tmux panel，支持并行任务

### 1.3 与 jca 的关系

| 特性               | jcad                | jca                                |
| ------------------ | ------------------- | ---------------------------------- |
| 自动启用非交互模式 | ✅ 是               | ⚠️ 需手动指定 `-n`                 |
| 自动启用 worktree  | ✅ 是               | ⚠️ 需手动指定 `-w` 或 `--worktree` |
| 自动启用 dispatch  | ✅ 是               | ⚠️ 需手动指定 `--dispatch`         |
| 多行任务自动处理   | ✅ 自动创建临时文件 | ⚠️ 需手动指定 `--task-file`        |
| 交互模式           | ✅ 支持             | ✅ 支持                            |

**适用场景**：

- 使用 `jcad`：快速启动代码任务，需要 worktree 隔离和自动派发
- 使用 `jca`：需要精细控制每个参数，或需要交互式会话

---

## 2. 基础用法

### 2.1 直接命令模式

最简单的使用方式，直接在命令行传递任务描述：

```bash
# 单行任务
jcad "重构用户认证模块，使用新的加密算法"

# 代码生成任务
jcad "创建一个用户注册 API，包含输入验证和错误处理"

# 代码优化任务
jcad "优化数据库查询性能，添加必要的索引"
```

### 2.2 交互式输入模式

不传递参数时进入交互模式，支持多行输入：

```bash
jcad
```

进入交互模式后：

- 输入任务内容（支持多行，按 `Enter` 换行）
- 按 `Ctrl+J` 或 `Ctrl+]` 确认提交
- 系统会自动创建临时文件并派发任务

**交互模式示例**：

```text
请输入任务内容（Ctrl+J/Ctrl+] 确认，Enter 换行）：
> 重构订单处理模块
> 1. 将订单状态机提取到独立类
> 2. 实现订单锁机制防止并发冲突
> 3. 添加订单操作的审计日志
> 背景信息：当前在高并发场景下出现订单状态不一致问题

[按 Ctrl+J 确认]
📝 临时文件已创建: /tmp/jcad_task_xxxxxxxx.txt
```

### 2.3 任务文件模式

对于复杂的任务描述，可以预先编写任务文件：

```bash
# 创建任务文件
cat > my_task.txt << 'EOF'
任务描述：重构支付模块

1. 将支付逻辑从订单模块中解耦
2. 实现支付状态机
3. 集成多种支付网关（支付宝、微信支付）
4. 添加支付超时处理和重试机制

技术要求：
- 使用策略模式实现多支付网关
- 添加单元测试覆盖核心逻辑
- 确保事务一致性

背景信息：
- 当前支付逻辑耦合在订单模块中，难以维护
- 需要支持新的支付渠道
EOF

# 直接指定任务文件
jcad my_task.txt
```

#### ⚠️ 重要提示：文件判断逻辑

`jcad` 通过检查文件是否存在来判断输入是任务文件还是任务内容：

- 如果文件 `my_task.txt` **存在** → 作为任务文件处理（使用 `--task-file` 参数）
- 如果文件 `my_task.txt` **不存在** → 作为任务内容处理（使用 `--task` 参数，即把 `my_task.txt` 当作任务描述）

**最佳实践建议**：

1. **确保文件已创建**：在使用 `jcad my_task.txt` 前，请确保文件已存在
2. **使用绝对路径**：推荐使用绝对路径，如 `jcad /path/to/my_task.txt`，避免路径问题
3. **验证文件内容**：可以先执行 `cat my_task.txt` 确认文件内容正确

**多行命令直接输入**：

```bash
# 使用双引号包裹多行命令（注意转义）
jcad "
重构用户管理模块
1. 将用户验证逻辑提取到独立服务类
2. 实现用户权限缓存机制
3. 添加用户操作审计日志
"
```

---

## 3. 核心功能解析

### 3.1 自动启用的工作模式

`jcad` 会自动启用以下三个关键模式，简化任务启动：

#### 非交互模式（`-n`）

- 不进入交互式会话，直接执行任务
- 适合自动化脚本和快速任务派发

#### 工作树模式（`--worktree`）

- 在独立的 Git worktree 中执行任务
- 隔离开发环境，避免污染主分支
- 自动管理 worktree 的创建、使用和清理

#### 任务派发（`--dispatch`）

- 使用 Tmux 创建独立的 panel 执行任务
- 支持并行执行多个任务
- 任务在后台运行，不阻塞当前终端

### 3.2 多行任务处理机制

`jcad` 内部自动处理多行任务：

```python
# 伪代码流程
if "\n" in task:
    # 检测到多行内容
    temp_file = create_temp_file(task)
    run_jca_dispatch(temp_file, is_dispatch_mode=True, force_dispatch=True)
else:
    # 单行内容直接传递
    run_jca_dispatch(task)
```

**关键点**：

- 多行任务自动转换为临时文件
- 临时文件保存在 `/tmp` 目录下
- 文件名格式：`jcad_task_{timestamp}.txt`

### 3.3 Worktree 隔离开发

Worktree 模式是 `jcad` 的核心安全特性：

#### 工作流程

1. **创建 worktree**
   - 自动生成唯一分支名：`jarvis-{project_name}-{timestamp}-{random_suffix}`
   - 在该分支上创建 git worktree
   - 如果仓库没有初始提交，自动创建初始提交

2. **链接配置**
   - 将原仓库的 `.jarvis` 目录软链接到 worktree
   - 确保配置和数据的一致性

3. **自动提交未保存更改**
   - 检测工作区是否有未提交的更改
   - 自动提交这些更改，确保任务执行前工作区干净

4. **执行任务**
   - 在 worktree 目录中执行代码修改
   - 所有变更都在独立分支上进行

5. **合并回主分支**
   - 任务完成后，使用 rebase 策略变基到原分支
   - 通过 fast-forward 合并
   - 保持线性 Git 历史

6. **清理资源**
   - 自动删除 worktree 目录
   - 删除对应的临时分支

#### 核心优势

| 优势       | 说明                        |
| ---------- | --------------------------- |
| 隔离开发   | 不会影响主分支的稳定性      |
| 自动管理   | 无需手动创建和删除 worktree |
| 软链接支持 | 配置和数据自动同步          |
| 智能合并   | 使用 rebase 保持历史清晰    |
| 自动清理   | 任务完成后自动释放资源      |

### 3.4 Tmux 派发集成

`jcad` 智能调度任务到 tmux panel，根据任务类型采用不同的调用方式：

#### 多行任务或交互模式（使用 Tmux）

对于多行任务或交互式输入，jcad 使用 tmux 的 `dispatch_command_to_panel` 函数创建新的 panel：

```bash
# 内部执行的命令（tmux 派发模式）
cd /path/to/project && jca -n -w --task-file '/tmp/jcad_task_xxxxxxxx.txt'
```

**注意**：在 tmux 派发模式下，jca 命令本身不需要 `--dispatch` 参数，因为 tmux 的 panel 创建已经完成了任务派发。

#### 单行任务（直接执行）

对于单行任务，jcad 直接执行 jca 命令并传递 `--dispatch` 参数：

```bash
# 内部执行的命令（直接派发模式）
jca -n -w --dispatch --task '你的任务内容'
```

**特性**：

- 自动查找或创建 tmux session
- 使用智能调度函数分配 panel
- 支持多个任务并行执行
- 父进程退出，不等待子进程完成

---

## 4. 最佳实践场景

### 4.1 快速原型开发

**场景**：需要快速验证一个想法或实现一个新功能。

```bash
# 示例：快速实现一个新的 API 端点
jcad "创建产品列表 API，支持分页和排序"
```

**优势**：

- worktree 隔离，不影响主分支
- 快速迭代，失败即弃
- 自动清理，无遗留垃圾

### 4.2 复杂重构任务

**场景**：需要重构大量代码，涉及多个文件。

```bash
# 使用任务文件详细描述重构任务
cat > refactor_auth.txt << 'EOF'
重构认证模块：

目标：将认证逻辑从各模块中解耦，统一到认证服务

具体步骤：
1. 创建 AuthenticationService 类
2. 将 user_auth、admin_auth 中的验证逻辑迁移
3. 实现统一的 Token 管理机制
4. 更新所有调用点

技术要求：
- 保持现有 API 兼容性
- 添加集成测试
- 更新相关文档
EOF

jcad refactor_auth.txt
```

**优势**：

- 详细的任务描述减少误解
- worktree 隔离保证主分支安全
- 自动合并策略保持历史清晰

### 4.3 并行任务处理

**场景**：同时处理多个独立的代码任务。

```bash
# 终端 1：处理用户模块
jcad "重构用户模块的验证逻辑"

# 终端 2：处理订单模块
jcad "优化订单查询性能"

# 终端 3：添加新功能
jcad "实现商品推荐功能"
```

**优势**：

- 每个任务在独立的 tmux panel 中运行
- 不会相互干扰
- 可以同时监控多个任务进度

### 4.4 安全隔离开发

**场景**：实验性代码或高风险改动。

```bash
# 实验性功能开发
jcad "尝试新的内存池实现（实验性）"

# 大规模重构
jcad "将单体应用拆分为微服务架构"
```

**优势**：

- 完全隔离，失败不会污染主分支
- 自动清理，无遗留分支
- 可以随时放弃，安全回退

---

## 5. 高级技巧

### 5.1 工具链集成

#### 与 Git 工作流集成

```bash
# 在 feature 分支上使用 jcad
git checkout -b feature/new-api
jcad "实现新的用户 API"
# 任务完成后，worktree 会自动合并回当前分支
```

#### 与 CI/CD 集成

```yaml
# 示例：在 CI 脚本中使用
- name: 自动化代码修复
  run: |
    jcad "修复代码中的 lint 错误"
    # 等待任务完成（根据实际情况调整）
    sleep 300
```

### 5.2 自定义配置

虽然 `jcad` 会自动启用某些参数，但你仍可以通过修改源码或环境变量来自定义行为。

#### 调整临时文件目录

默认临时文件保存在 `/tmp`，可以在 `jcad_cli.py` 中修改：

```python
dir="/tmp",  # 修改为其他目录
```

#### 调整 Tmux 行为

```python
stay_in_session_after_exit=True,  # 任务结束后是否保持 session
shell_fallback=False,  # 是否允许 shell fallback
```

### 5.3 性能优化

#### 批量任务处理

对于大量相似任务，可以编写脚本批量派发：

```bash
#!/bin/bash
# batch_refactor.sh

modules=("user" "order" "product" "payment")

for module in "${modules[@]}"; do
  echo "Refactoring $module module..."
  jcad "重构 $module 模块，添加单元测试和文档"
  sleep 5  # 避免同时启动过多任务
  echo "Dispatched $module task"
done

echo "All tasks dispatched!"
```

#### 减少等待时间

- 使用任务文件减少输入时间
- 并行执行独立任务
- 使用 tmux attach 监控进度

---

## 6. 注意事项与常见问题

### 6.1 临时文件管理

**问题**：临时文件会占用磁盘空间吗？

**解答**：

- 临时文件保存在 `/tmp` 目录下
- 系统重启时会自动清理
- 手动清理：`rm /tmp/jcad_task_*`

**建议**：

- 定期检查 `/tmp` 目录
- 避免在任务文件中包含敏感信息

### 6.2 Worktree 分支清理

**问题**：任务失败后，worktree 分支会残留吗？

**解答**：

- `jcad` 会自动清理 worktree 和分支
- 如果异常退出，可能需要手动清理

**手动清理命令**：

```bash
# 查看所有 worktree
git worktree list

# 删除指定 worktree
git worktree remove <worktree-path>

# 查看所有分支（包括 worktree 分支）
git branch -a

# 删除已合并的分支
git branch -d <branch-name>

# 强制删除分支
git branch -D <branch-name>
```

### 6.3 Tmux 依赖

**问题**：必须使用 tmux 吗？

**解答**：

- `jcad` 的 dispatch 模式依赖 tmux
- 如果没有 tmux，可以考虑直接使用 `jca` 命令

**不使用 tmux 的替代方案**：

```bash
# 直接使用 jca，不使用 dispatch
jca -n -w -r "你的任务"
```

### 6.4 故障排查

#### 问题：找不到 jca 命令

**错误信息**：

```text
❌ 错误: 找不到 'jca' 命令，请确保 jarvis 已正确安装
```

**解决方案**：

1. 确认 jarvis 已正确安装：`pip list | grep jarvis`
2. 检查 PATH 环境变量
3. 重新安装 jarvis

#### 问题：tmux panel 创建失败

**错误信息**：

```text
❌ 错误: dispatch 模式创建 tmux panel 失败
```

**解决方案**：

1. 确认 tmux 已安装：`tmux -V`
2. 检查 tmux 是否正常运行：`tmux ls`
3. 尝试手动创建 tmux session：`tmux new -s test`

#### 问题：worktree 创建失败

**错误信息**：

```text
fatal: working tree 'xxx' already exists
```

**解决方案**：

1. 查看现有 worktree：`git worktree list`
2. 删除冲突的 worktree：`git worktree remove <path>`
3. 重试任务

#### 问题：任务内容为空

**错误信息**：

```text
❌ 错误: 任务内容为空，无法执行
```

**解决方案**：

1. 检查任务文件是否存在：`ls -la my_task.txt`
2. 确认任务文件内容不为空：`cat my_task.txt`
3. 检查文件路径是否正确

### 6.5 最佳实践总结

| 原则         | 说明                               |
| ------------ | ---------------------------------- |
| 任务描述清晰 | 详细描述任务目标、步骤和要求       |
| 使用任务文件 | 复杂任务使用文件而非命令行参数     |
| 合理并行     | 独立任务可以并行执行，相关任务串行 |
| 监控进度     | 使用 tmux attach 查看任务进度      |
| 定期清理     | 定期检查并清理临时文件和 worktree  |
| 备份重要数据 | 在大规模重构前备份代码             |
| 测试验证     | 任务完成后充分测试                 |
| 文档更新     | 及时更新相关文档                   |

---

## 7. 参考资料

- [Jarvis 使用指南](../jarvis_book/4.使用指南.md)
- [jca 命令文档](../jarvis_book/4.使用指南.md)
- [Git Worktree 官方文档](https://git-scm.com/docs/git-worktree)
- [Tmux 官方文档](https://github.com/tmux/tmux/wiki)

---

**文档版本**：v1.0  
**最后更新**：2025-01-12  
**维护者**：Jarvis Team

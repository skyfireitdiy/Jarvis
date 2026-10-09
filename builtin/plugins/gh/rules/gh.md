---
name: gh_rule
description: 当需要自动处理 GitHub 仓库的 PR 或 Issue 时触发。每当用户提及"处理 PR"、"处理 issue"、"合并 PR"、"查看 PR"、"关闭 issue"、"评论 issue"、"gh 插件"、"GitHub 助手"时触发。
---

# gh 插件使用规则

此规则定义了 gh 插件（GitHub 助手）的使用方式，指导 Agent 按**标准工作流**处理当前仓库的 PR 和 Issue，并在**关键节点与用户确认**后再执行不可逆操作。

## 能力清单

gh 插件复用 GitHub 官方 `gh` CLI 完成 GitHub 操作（通过 `execute_script` 执行 `gh` 命令）。插件本身不提供独立工具，Agent 直接调用 `gh` 命令：

| 能力       | 命令                                 | 类型   | 说明                       |
| ---------- | ------------------------------------ | ------ | -------------------------- |
| 列出 PR    | `gh pr list`                         | 读操作 | 按 state 列出 Pull Request |
| 查看 PR    | `gh pr view <number>`                | 读操作 | 查看单个 PR 详情           |
| 合并 PR    | `gh pr merge <number>`               | 写操作 | 合并 PR（需认证）          |
| 列出 Issue | `gh issue list`                      | 读操作 | 按 state 列出 Issue        |
| 查看 Issue | `gh issue view <number>`             | 读操作 | 查看单个 Issue 详情        |
| 评论       | `gh issue comment` / `gh pr comment` | 写操作 | 对 PR/Issue 评论（需认证） |
| 关闭 Issue | `gh issue close <number>`            | 写操作 | 关闭 Issue（需认证）       |

> 读操作（列出/查看）公开仓库匿名可访问；写操作（合并/评论/关闭）必须已登录 token。

**常用命令示例**：

```bash
# 列出当前仓库 open 的 issue / PR
gh issue list
gh pr list

# 查看单个 issue / PR 详情（含 body、labels、merged/mergeable 状态）
gh issue view 60
gh pr view 123

# 发布评论
gh issue comment 60 --body "评论内容"
gh pr comment 123 --body "评论内容"

# 关闭 issue（不可逆）
gh issue close 60

# 合并 PR（不可逆，可指定 --squash / --rebase / --merge）
gh pr merge 123 --squash
```

## 默认仓库

gh 插件默认处理**当前工作目录对应的 GitHub 仓库**（读取 git remote origin 自动解析）。若当前目录不是 git 仓库或缺少 origin remote，请先确认目标仓库，或用 `gh repo set-default owner/repo` 指定，或命令加 `--repo owner/repo` 参数显式指定。

**开始任何操作前，先确认目标仓库**：若用户未指定仓库，先通过 `gh issue list`/`gh pr list` 或向用户确认当前要操作哪个仓库，避免对错仓库执行操作。

## 认证流程

1. **读操作**（列出/查看 PR、issue）：公开仓库匿名可访问，无需认证，直接执行。
2. **写操作**（合并 PR、评论、关闭 issue）：**必须先认证**。若命令返回"未登录"提示，引导用户在终端执行：

   ```bash
   gh auth login
   ```

   插件复用 GitHub 官方 gh CLI 登录态，后续写操作自动使用该 token。

3. 可用 `gh auth status` 查看是否已登录。

## Issue 处理标准工作流

处理 issue 时按下述顺序执行，**每一步都要基于上一步的结果**，不要跳步或臆测：

### 1. 定位与确认目标

- 用 `gh issue list`（默认 `open`）列出当前仓库的 issue，向用户确认要处理哪个（按编号）。
- 若用户只给编号，用 `gh issue view <number>` 查看该 issue 详情（标题、作者、body、labels、状态），**先复述 issue 内容确认理解正确**，再继续。

### 2. 处理（读/分析为主）

- 阅读 issue 的 `body` 与现有评论，判断问题类型（bug / 需求 / 疑问）。
- 如需了解上下文，可查看相关代码或文档，形成处理方案。

### 3. 关键节点确认（写操作前必须确认）

- **评论前**：向用户确认评论内容与措辞，确认发布到正确的 issue 编号后再 `gh issue comment`。评论末尾**必须**附加「评论标识」章节定义的固定"自动处理"标识。
- **关闭前**：关闭是**不可逆**操作。必须向用户确认"是否关闭 issue #N"，得到明确同意后再 `gh issue close`。不要因 issue 看起来已解决就擅自关闭。

### 4. 收尾

- 操作完成后，向用户汇报结果（评论已发布 / issue 已关闭）。

## PR 处理标准工作流

处理 PR 时按下述顺序执行：

### 1. 定位与确认目标

- 用 `gh pr list`（默认 `open`）列出当前仓库的 PR，向用户确认要处理哪个（按编号）。
- 若用户只给编号，用 `gh pr view <number>` 查看该 PR 详情（标题、作者、state、`merged`、`mergeable`、head/base 分支、body）。

### 2. 合并前检查（合并 PR 的必经步骤）

- **查看 PR 状态**：用 `gh pr view <number> --json state,merged,mergeable,headRefName,baseRefName,title,body` 确认：
  - `state` 是否为 `open`；
  - `merged` 是否为 `false`（已合并的 PR 不能重复合并）；
  - `mergeable` 是否为 `true`（`false` 表示存在冲突，**不能合并**，需先解决冲突；`null` 表示 GitHub 仍在计算，稍后重试）。
- 阅读 PR 的 `body` 与改动说明，理解变更内容。
- **只有 PR 可合并（open、未合并、无冲突）时，才进入下一步**；否则向用户说明原因（如冲突），不要强行合并。

### 3. 关键节点确认（合并前必须确认）

- **合并是高风险不可逆操作**，必须向用户确认：
  - 要合并的 PR 编号与标题；
  - 合并方式（`--squash` / `--rebase` / `--merge`，默认 `merge`，可按需指定）。
- 得到用户明确同意后，才执行 `gh pr merge`。

### 4. 评论（可选）

- 若需在 PR 上补充说明，先向用户确认评论内容，再 `gh pr comment`。评论末尾**必须**附加「评论标识」章节定义的固定"自动处理"标识。

### 5. 收尾

- 合并成功后向用户汇报结果（PR #N 已合并，合并方式）。

## 评论标识（自动处理声明）

**所有由 gh 插件自动发布的评论（issue 或 PR），必须在评论末尾附加固定的"自动处理"标识**，表明该评论由 Jarvis GitHub 插件自动生成，便于读者识别。

固定标识（Markdown）：

```markdown
---

> 🤖 此评论由 Jarvis GitHub 插件自动处理
```

- 标识放在评论**末尾**，与正文之间用 `---` 分隔。
- **必须原样使用上述固定文本**，不得改动措辞或样式。
- 仅当评论是**插件自动发布**时才附加；若评论内容需要伪装成人工发布，则不符合本规则，不应发布。

**评论示例**：

```markdown
感谢反馈！我们已实现该配置示例并合入文档。

---

> 🤖 此评论由 Jarvis GitHub 插件自动处理
```

## 代码提交

处理 issue/PR 过程中若**修改了代码**，CodeAgent 每次变更都会自动生成一个以 `CheckPoint #N` 开头的临时提交（仅用于过程回退，不应直接进入历史）。当需求真正完成时，**必须调用 `commit` 工具**生成正式提交——它会自动把这些 CheckPoint 临时提交压缩为一个正式提交（用 LLM 生成提交信息）。

- 代码改动完成后、汇报结果前，调用 `commit` 工具提交。
- 不要直接把 `CheckPoint #N` 临时提交当作最终结果汇报；正式提交由 `commit` 工具生成。
- 若用户要求手动提交或指定提交信息，可改用 `git commit` 并遵循用户要求。

## 代码改动走 PR（开源规范流程）

**凡涉及代码/文档改动的处理，默认遵循开源协作规范：在特性分支上完成，通过 Pull Request 合入主干，不直接向 `main` 提交。** 这与 [CONTRIBUTING.md](../../../../CONTRIBUTING.md) 的「Fork + 特性分支 + PR」要求一致。

### 标准流程

1. **确认基线**：先 `git fetch origin` 并确认当前主干（默认 `main`）状态，避免基于过期历史。
2. **建特性分支**：从主干切出语义化命名的分支，如 `feat/<主题>`、`fix/<主题>`、`docs/<主题>`。
3. **在分支上完成改动并提交**：改动完成后调用 `commit` 工具生成正式提交（见上节）。
4. **推送分支**：`git push -u origin <分支名>`。
5. **创建 PR**：用 `gh pr create --base main --head <分支名> --title <标题> --body-file <描述文件>` 创建 PR，描述需包含：背景、改动清单、验证方式。
6. **关联 Issue**：若该 PR 解决某个 Issue，在 PR 描述中用 `Closes #<编号>` 关联（合并后自动关闭）；不要在处理过程中提前手动关闭 Issue。
7. **收尾汇报**：向用户汇报 PR 链接与状态。

### 约束

- **不要直接向 `main` 提交代码改动**；若发现改动已在 `main` 上且尚未推送，应先将其移到特性分支再推送主干。
- 一个 PR 聚焦一件事（一个功能/修复/文档主题），避免把不相关改动混在同一 PR。
- PR 标题遵循提交规范（`feat:` / `fix:` / `docs:` / `refactor:` 等）。
- 创建 PR、推送分支前，若涉及对外可见或改写历史等影响面较大的操作，先与用户确认。

### 例外

- 用户明确要求直接提交到 `main`（如紧急修复、个人仓库快速迭代）时，遵从用户要求。
- 纯只读操作、评论、关闭 Issue 等不涉及代码改动的处理，无需走 PR。

## 关键节点确认总则

以下操作**必须先与用户确认，得到明确同意后才能执行**，不得擅自进行：

1. **关闭 issue**（不可逆）。
2. **合并 PR**（不可逆，且需确认合并方式）。
3. **发布评论**（内容对外可见，需确认措辞与目标编号）。
4. **跨仓库操作**（`--repo` 指向非当前仓库时，先确认）。

确认时应给出**具体信息**（编号、标题、拟执行动作），让用户能明确判断，而非笼统地问"是否继续"。

## 安全提示

- token 是敏感凭据，**不要**在评论、日志或输出中泄露完整 token。
- 合并/关闭等不可逆操作，执行前**必须**向用户确认（见上）。
- 写操作失败返回 401/403 时，提示用户重新登录（token 可能失效）。
- 不要对**不是用户要求**的 issue/PR 执行写操作。

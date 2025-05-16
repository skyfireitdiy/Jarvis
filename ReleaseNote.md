### Release Note - v0.1.168  

#### **新功能 (Features)**  
- **Git 分析器**: 支持分析 commit 范围并重构分析逻辑 (`git-analyzer`)  
- **配置项**: 新增 `JARVIS_AUTO_UPDATE` 配置项，支持 Git 仓库自动检查更新 (`config`, `git_utils`)  
- **平台支持**: 为平台添加 Web 功能支持检查 (`platform`)  
- **安装命令**: 为 `install` 命令添加 shell 类型参数支持 (`install`)  
- **大文件处理**: 优化大文件处理逻辑，并添加对大内容大小的检查 (`base`, `workflow`)  

#### **修复 (Fixes)**  
- **Git 工具**:  
  - 修复提取分析报告时未返回原始结果的问题 (`git_details`)  
  - 修复 Git 仓库更新后未恢复工作目录的问题 (`git_utils`)  
- **Jarvis Agent**:  
  - 修正任务完成提示的变量名错误 (`jarvis_agent`)  
  - 修正任务完成提示的格式和内容 (`jarvis_agent`)  

#### **优化与重构 (Refactors & Improvements)**  
- **代码提交流程**: 简化提交流程并优化大文件处理 (`workflow`)  
- **Web 工具**: 将 `check` 方法改为静态方法 (`web_tools`)  

#### **文档更新 (Documentation)**  
- **发布流程**: 完善版本发布流程说明并新增 `ReleaseNote` 文件 (`发布流程`)  
- **代码审查报告**: 更新输出格式说明 (`code_review`)  
- **README**:  
  - 补充 `JARVIS_AUTO_UPDATE` 配置项说明  
  - 移除已弃用的 `OPENAI_MODEL_NAME` 配置项  
  - 新增技术支持群二维码图片  
- **微信支持**: 添加微信二维码图片 (`wechat`)  

#### **其他 (Miscellaneous)**  
- 自动提交版本发布前的变更 (`Auto commit before version release`)  
- 版本发布准备 (`chore(release)`)  

本次更新主要围绕 **Git 分析优化、配置项增强、Bug 修复及文档完善**，提升稳定性和用户体验。
分析当前项目的实际结构，基于15维度开发规范框架，为该项目生成定制化的开发规则。

任务要求：

1. 扫描项目目录结构，识别项目类型（Python/Node.js/Java等）
2. 分析现有代码风格、配置文件、依赖管理
3. 检查版本控制配置（git分支、提交规范）
4. 识别测试框架和测试覆盖率要求
5. 基于实际项目特点，为每个维度生成具体规则
6. 将规则写入.jarvis/rules/目录，每个维度一个文件

15个维度规则文件：

- 01_encoding_standards.yaml - 编码规范
- 02_project_structure.yaml - 工程结构规范  
- 03_error_handling.yaml - 错误处理规范
- 04_data_processing.yaml - 数据处理规范
- 05_api_design.yaml - 接口设计规范
- 06_performance.yaml - 性能与资源规范
- 07_version_control.yaml - 版本控制规范
- 08_documentation.yaml - 文档规范
- 09_collaboration.yaml - 协作流程规范
- 10_testing.yaml - 测试规范
- 11_code_review.yaml - 代码评审规范
- 12_security.yaml - 安全规范
- 13_build_deploy.yaml - 构建部署规范
- 14_logging_monitoring.yaml - 日志监控规范
- 15_disaster_recovery.yaml - 容灾备份规范

输出格式：每个文件使用YAML格式，包含具体规则和检查项

生成原则：

- 根据项目实际特点，如果某些维度与项目无关，可以不生成对应规则文件
- 例如：纯前端项目可以不生成"13_build_deploy.yaml"中的部署规范
- 单文件脚本项目可以不生成"02_project_structure.yaml"中的工程结构规范
- 每个生成的规则文件都应有明确的项目上下文关联

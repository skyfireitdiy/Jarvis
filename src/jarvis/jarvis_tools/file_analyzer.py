from typing import Dict, Any
import os
import pathlib

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class FileAnalyzerTool:
    """
    单文件分析工具
    使用agent深入分析单个文件的结构、实现细节和代码质量
    """

    name = "file_analyzer"
    description = "深入分析单个文件的结构、实现细节和代码质量"
    labels = ['code', 'analysis', 'file']
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要分析的文件路径"
            },
            "root_dir": {
                "type": "string",
                "description": "项目根目录路径（可选）",
                "default": "."
            },
            "objective": {
                "type": "string",
                "description": "描述本次文件分析的目标和用途，例如'准备重构该文件'或'理解该文件在项目中的作用'",
                "default": ""
            }
        },
        "required": ["file_path"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单文件分析工具

        Args:
            args: 包含参数的字典

        Returns:
            包含执行结果的字典
        """
        # 存储原始目录
        original_dir = os.getcwd()

        try:
            # 解析参数
            file_path = args.get("file_path", "")
            root_dir = args.get("root_dir", ".")
            objective = args.get("objective", "")

            # 验证参数
            if not file_path:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供文件路径"
                }

            # 确保文件路径是相对于root_dir的，如果是绝对路径则转换为相对路径
            abs_file_path = os.path.abspath(file_path)
            abs_root_dir = os.path.abspath(root_dir)

            if abs_file_path.startswith(abs_root_dir):
                rel_file_path = os.path.relpath(abs_file_path, abs_root_dir)
            else:
                rel_file_path = file_path

            # 获取文件扩展名和文件名
            file_ext = pathlib.Path(file_path).suffix
            file_name = os.path.basename(file_path)

            # 创建agent的system prompt
            system_prompt = self._create_system_prompt(
                rel_file_path, file_name, file_ext, root_dir, objective
            )

            # 创建agent的summary prompt
            summary_prompt = self._create_summary_prompt(rel_file_path, file_name)

            # 切换到根目录
            os.chdir(root_dir)

            # 检查文件是否存在
            if not os.path.isfile(rel_file_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"文件不存在: {rel_file_path}"
                }

            # 构建使用的工具
            from jarvis.jarvis_tools.registry import ToolRegistry
            tool_registry = ToolRegistry()
            tool_registry.use_tools([
                "execute_shell",
                "read_code",
                "find_symbol",
                "function_analyzer",
                "find_caller"
            ])

            # 创建并运行agent
            analyzer_agent = Agent(
                system_prompt=system_prompt,
                name=f"FileAnalyzer-{file_name}",
                description=f"分析 {file_name} 文件的结构和实现",
                summary_prompt=summary_prompt,
                platform=PlatformRegistry().get_normal_platform(),
                output_handler=[tool_registry],
                execute_tool_confirm=False,
                auto_complete=True
            )

            # 运行agent并获取结果
            task_input = f"深入分析文件 {rel_file_path} 的结构、实现细节和代码质量"
            result = analyzer_agent.run(task_input)

            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"文件分析失败: {str(e)}"
            }
        finally:
            # 恢复原始目录
            os.chdir(original_dir)

    def _create_system_prompt(self, file_path: str, file_name: str, file_ext: str,
                             root_dir: str, objective: str) -> str:
        """
        创建Agent的system prompt

        Args:
            file_path: 文件路径
            file_name: 文件名
            file_ext: 文件扩展名
            root_dir: 代码库根目录
            objective: 分析目标

        Returns:
            系统提示文本
        """
        objective_text = f"\n\n## 分析目标\n{objective}" if objective else ""

        return f"""# 文件分析专家

## 任务描述
分析文件 `{file_path}` 的结构、实现细节和代码质量，专注于分析目标所需的内容，生成有针对性、深入且有洞察力的文件分析报告。{objective_text}

## 工具使用优先级
1. **优先使用 read_code**: 直接读取文件内容是分析文件的首选方式
2. **优先使用 execute_shell**:
   - 使用 rg 搜索文件内容: `rg "pattern" {file_path}`
   - 使用 loc 统计代码: `loc {file_path}`
3. **仅在必要时使用其他分析工具**

## 文件信息
- 文件路径: `{file_path}`
- 文件名称: `{file_name}`
- 文件类型: `{file_ext}`
- 项目根目录: `{root_dir}`

## 分析策略
1. 首先使用read_code直接读取整个文件内容或分段读取
2. 使用rg命令搜索文件中的特定模式和结构
3. 使用loc命令获取文件统计信息
4. 根据文件类型和分析目标确定重点关注的方面
5. 保证分析的完整性，收集充分的信息后再得出结论

## 分析步骤
以下步骤应根据具体分析目标灵活应用:

1. **文件基本信息分析**:
   - 使用 `loc {file_path}` 获取代码统计
   - 使用 read_code 读取文件头部注释和文档
   - 确定文件的编程语言和主要功能

2. **结构分析**:
   - 使用 read_code 阅读完整文件
   - 对于大文件，可分段读取主要部分
   - 识别文件的主要组成部分:
     - 类定义: `rg "class\\s+" {file_path}`
     - 函数定义: `rg "def\\s+|function\\s+" {file_path}`
     - 重要变量: `rg "const\\s+|var\\s+|let\\s+" {file_path}`

3. **核心组件分析**:
   - 识别文件中的关键接口、类和函数
   - 使用 rg 搜索重要的代码模式
   - 分析组件间的交互和依赖关系

4. **实现细节分析**:
   - 读取并分析关键函数的实现
   - 关注异常处理: `rg "try|catch|except" {file_path}`
   - 检查资源管理: `rg "open|close|with" {file_path}`

5. **引用分析**:
   - 找出引用的外部依赖: `rg "import|require|include" {file_path}`
   - 分析与其他模块的交互

## 分析工具使用指南

### read_code
- **首选工具**: 用于读取和分析文件内容
- **用法指南**:
  - 读取整个文件: 直接指定文件路径
  - 读取部分内容: 指定文件路径和行范围
  - 读取头部或关键部分: 根据目的选择合适的行范围

### execute_shell
- **用途**: 执行辅助命令进行分析
- **推荐命令**:
  - `rg "pattern" {file_path}`: 在文件中搜索模式
  - `loc {file_path}`: 获取文件代码统计
  - `rg -n "class|def|function" {file_path}`: 查找结构元素

### 其他专业工具
- **使用时机**: 仅当read_code和execute_shell不足以完成分析时
- **使用前提**: 必须先尝试使用基本工具解决问题
- **选择原则**: 根据实际需要选择最简洁有效的工具

## 分析框架适应
根据文件类型和编程范式调整分析重点:

### 不同编程范式
- 面向对象: 类层次、继承、封装、接口实现
- 函数式: 函数组合、不可变性、纯函数
- 过程式: 流程控制、状态管理、数据处理
- 声明式: 规则定义、约束表达、模式匹配

### 不同文件类型
- 源代码文件: 实现逻辑、算法、接口设计
- 配置文件: 参数设置、环境变量、系统选项
- 模板文件: 渲染逻辑、变量占位符、条件分支
- 数据文件: 结构组织、关系定义、索引设计

## 输出要求
- 直接回应分析目标的关键问题
- 提供与目标相关的深入洞察
- 分析内容应直接服务于分析目标
- 避免与目标无关的冗余信息
- 使用具体代码片段支持分析结论
- 提供针对分析目标的具体建议
- 保证全面分析相关信息后再得出结论"""

    def _create_summary_prompt(self, file_path: str, file_name: str) -> str:
        """
        创建Agent的summary prompt

        Args:
            file_path: 文件路径
            file_name: 文件名

        Returns:
            总结提示文本
        """
        return f"""# 文件分析报告: `{file_name}`

## 报告要求
生成一份完全以分析目标为导向的文件分析报告。不要遵循固定的报告模板，而是完全根据分析目标来组织内容：

- 专注回答分析目标提出的问题
- 只包含与分析目标直接相关的发现和洞察
- 完全跳过与分析目标无关的内容，无需做全面分析
- 分析深度应与目标的具体需求匹配
- 使用具体的代码片段和实例支持你的观点
- 以清晰的Markdown格式呈现，简洁明了

在分析中保持灵活性，避免固定思维模式。你的任务不是提供全面的文件概览，而是直接解决分析目标中提出的具体问题。"""
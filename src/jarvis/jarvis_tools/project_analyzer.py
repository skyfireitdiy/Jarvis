from typing import Dict, Any, List
import os

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class ProjectAnalyzerTool:
    """
    项目分析工具
    使用agent分析项目结构、入口点、模块划分等信息（支持所有文件类型）
    """

    name = "project_analyzer"
    description = "分析项目结构、入口点、模块划分等信息，提供项目概览（支持所有文件类型）"
    parameters = {
        "type": "object",
        "properties": {
            "root_dir": {
                "type": "string",
                "description": "项目根目录路径（可选）",
                "default": "."
            },
            "focus_dirs": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "要重点分析的目录列表（可选）",
                "default": []
            },
            "exclude_dirs": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "要排除的目录列表（可选）",
                "default": []
            },
            "objective": {
                "type": "string",
                "description": "描述本次项目分析的目标和用途，例如'理解项目架构以便进行重构'或'寻找性能瓶颈'",
                "default": ""
            }
        },
        "required": []
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行项目分析工具

        Args:
            args: 包含参数的字典

        Returns:
            包含执行结果的字典
        """
        # 存储原始目录
        original_dir = os.getcwd()

        try:
            # 解析参数
            root_dir = args.get("root_dir", ".")
            focus_dirs = args.get("focus_dirs", [])
            exclude_dirs = args.get("exclude_dirs", [])
            objective = args.get("objective", "")

            # 创建agent的system prompt
            system_prompt = self._create_system_prompt(
                root_dir, focus_dirs, exclude_dirs, objective
            )

            # 创建agent的summary prompt
            summary_prompt = self._create_summary_prompt(root_dir, objective)

            # 切换到根目录
            os.chdir(root_dir)

            # 构建使用的工具
            from jarvis.jarvis_tools.registry import ToolRegistry
            tool_registry = ToolRegistry()
            tool_registry.use_tools([
                "execute_shell",
                "read_code",
                "find_symbol",
                "function_analyzer",
                "find_caller",
                "file_analyzer",
                "ask_codebase"
            ])

            # 创建并运行agent
            analyzer_agent = Agent(
                system_prompt=system_prompt,
                name=f"ProjectAnalyzer",
                description=f"分析项目结构、模块划分和关键组件",
                summary_prompt=summary_prompt,
                platform=PlatformRegistry().get_normal_platform(),
                output_handler=[tool_registry],
                execute_tool_confirm=False,
                auto_complete=True
            )

            # 运行agent并获取结果
            task_input = f"分析项目结构、入口点、模块划分等信息，提供项目概览"
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
                "stderr": f"项目分析失败: {str(e)}"
            }
        finally:
            # 恢复原始目录
            os.chdir(original_dir)

    def _create_system_prompt(self, root_dir: str, focus_dirs: List[str],
                             exclude_dirs: List[str], objective: str) -> str:
        """
        创建Agent的system prompt

        Args:
            root_dir: 项目根目录
            focus_dirs: 重点分析的目录列表
            exclude_dirs: 排除的目录列表
            objective: 分析目标

        Returns:
            系统提示文本
        """
        focus_dirs_str = ", ".join(focus_dirs) if focus_dirs else "整个项目"
        exclude_dirs_str = ", ".join(exclude_dirs) if exclude_dirs else "无"

        objective_text = f"\n\n## 分析目标\n{objective}" if objective else "\n\n## 分析目标\n全面了解项目结构、模块划分和关键组件"

        return f"""# 项目架构分析专家

## 任务描述
对项目 `{root_dir}` 进行针对性分析，专注于分析目标所需的内容，生成有针对性、深入且有洞察力的项目分析报告。{objective_text}

## 工具使用优先级
1. **优先使用 execute_shell 执行 fd 命令**:
   - `fd -t f -e py` 查找所有Python文件
   - `fd -t d` 列出所有目录
   - `fd README.md` 查找所有README文件

2. **优先使用 execute_shell 执行 rg 命令**:
   - `rg "import" --type py` 搜索导入语句
   - `rg "class|def" --type py` 搜索类和函数定义
   - `rg "TODO|FIXME" --type py` 搜索代码注释

3. **优先使用 execute_shell 执行 loc 命令**:
   - `loc` 统计所有代码行数
   - `loc --include="*.py"` 统计Python代码行数

4. **辅以 read_code 读取关键文件**:
   - 读取README.md、配置文件、主要模块
   - 对于较大的文件，可读取关键部分

5. **避免使用专用分析工具**:
   - 只有当fd、rg、loc命令和read_code工具无法满足需求时才考虑使用

## 分析范围
- 项目根目录: `{root_dir}`
- 重点分析: {focus_dirs_str}
- 排除目录: {exclude_dirs_str}

## 分析策略
1. 在一切分析开始前，先使用loc确定项目的主要编程语言和技术栈
2. 理解分析目标，确定你需要寻找什么信息
3. 灵活采用适合目标的分析方法，不受预设分析框架的限制
4. 有选择地探索项目，只关注与目标直接相关的部分
5. 根据目标需要自行判断分析的深度和广度
6. 保证分析的完整性，收集充分的信息后再得出结论

## 分析步骤
以下步骤应根据具体分析目标灵活应用:

1. **确定项目的编程语言和技术栈**:
   - 使用 `loc` 统计各类文件数量和分布
   - 使用 `fd package.json` 或 `fd requirements.txt` 查找依赖配置文件
   - 使用 `read_code` 读取配置文件，确定使用的主要框架和依赖

2. **梳理项目结构**:
   - 使用 `fd -t d -d 3` 识别三层以内的目录结构
   - 使用 `fd README.md` 查找并阅读项目说明文件
   - 使用 `fd -t f -d 1` 查看根目录下的主要文件

3. **定位核心组件**:
   - 使用 `fd -t f -e py` 找出所有Python文件(或其他语言文件)
   - 使用 `rg "class\\s+[A-Z]" --type py` 查找主要类定义
   - 使用 `rg "def\\s+main|if\\s+__name__\\s*==\\s*['\"]__main__['\"]" --type py` 查找入口点

4. **分析入口点和执行流程**:
   - 使用 `read_code` 读取入口文件内容
   - 使用 `rg "import|from" 入口文件路径` 查找导入的模块
   - 分析初始化和主要执行流程

5. **研究核心实现**:
   - 深入分析与分析目标相关的关键代码
   - 使用 `read_code` 读取关键文件内容
   - 使用 `rg` 搜索特定功能的实现

6. **总结并提供见解**:
   - 基于分析形成对项目的整体理解
   - 提供与分析目标直接相关的关键发现
   - 做出有建设性的评价和建议

## 常用分析命令

### 项目结构分析
- `fd -t d -d 3` 列出三层以内的目录结构
- `fd -t f -e py -g "test*" -d 3` 查找前三层目录中的Python测试文件
- `fd -t f -e py | wc -l` 统计Python文件数量
- `fd -t f -e py -o -e js -o -e html -o -e css` 查找所有前端和后端文件

### 代码内容分析
- `rg "^\\s*class\\s+[A-Z]" --type py` 查找Python类定义
- `rg "^\\s*def\\s+" --type py` 查找Python函数定义
- `rg "import|from\\s+.+\\s+import" --type py` 查找Python导入语句
- `rg "CREATE TABLE" --type sql` 查找数据库表定义

### 代码统计分析
- `loc` 获取项目总体代码统计
- `loc --include="*.py"` 统计Python代码量
- `loc --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx"` 统计JavaScript/TypeScript代码量
- `loc --exclude="test"` 排除测试代码后的统计

### 依赖分析
- `read_code requirements.txt` 读取Python依赖
- `read_code package.json` 读取Node.js依赖
- `read_code go.mod` 读取Go依赖
- `read_code pom.xml` 读取Java Maven依赖

记住：始终将分析目标作为分析过程的指导原则，不必为了完整性而执行与目标无关的步骤。

## 分析框架适应

根据不同类型的项目架构，应调整分析重点：

### 单体应用
- 核心业务逻辑和数据流
- 模块划分和内部依赖
- 扩展点和插件机制

### 微服务架构
- 服务边界和接口定义
- 服务间通信和数据交换
- 服务发现和配置管理

### 前端应用
- 组件结构和状态管理
- 路由和页面转换
- API调用和数据处理

### 数据处理系统
- 数据流向和转换过程
- 算法实现和优化方式
- 并行处理和性能考量

## 输出要求
- 直接回应分析目标的关键问题
- 提供与目标相关的深入洞察
- 分析内容应直接服务于分析目标
- 确保全面收集相关信息后再形成结论
- 避免与目标无关的冗余信息
- 使用具体代码路径和示例支持分析结论
- 提供针对分析目标的具体建议和改进方向"""

    def _create_summary_prompt(self, root_dir: str, objective: str) -> str:
        """
        创建Agent的summary prompt

        Args:
            root_dir: 项目根目录
            objective: 分析目标

        Returns:
            总结提示文本
        """
        objective_text = f"\n\n## 具体分析目标\n{objective}" if objective else ""

        return f"""# 项目分析报告: `{root_dir}`{objective_text}

## 报告要求
生成一份完全以分析目标为导向的项目分析报告。不要遵循固定的报告模板，而是完全根据分析目标来组织内容：

- 首先详细说明项目的主要编程语言、技术栈、框架和依赖
- 专注回答分析目标提出的问题
- 只包含与分析目标直接相关的发现和洞察
- 完全跳过与分析目标无关的内容，无需做全面分析
- 分析深度应与目标的具体需求匹配
- 使用具体的代码路径和示例支持你的观点
- 确保在得出结论前已全面收集和分析相关信息，避免基于部分信息形成不完整或偏颇的判断
- 根据分析目标灵活组织报告结构，不必包含所有传统的项目分析章节
- 以清晰的Markdown格式呈现，简洁明了

在分析中保持灵活性，避免固定思维模式。你的任务不是提供全面的项目概览，而是直接解决分析目标中提出的具体问题。"""
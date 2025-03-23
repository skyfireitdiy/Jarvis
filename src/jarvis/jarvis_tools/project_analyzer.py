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
                platform=PlatformRegistry().get_codegen_platform(),
                output_handler=[tool_registry],
                need_summary=True,
                is_sub_agent=True,
                use_methodology=False,
                record_methodology=False,
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

## 分析范围
- 项目根目录: `{root_dir}`
- 重点分析: {focus_dirs_str}
- 排除目录: {exclude_dirs_str}

## 分析策略
1. 在一切分析开始前，必须先确定项目的主要编程语言和技术栈
2. 理解分析目标，确定你需要寻找什么信息
3. 灵活采用适合目标的分析方法，不受预设分析框架的限制
4. 有选择地探索项目，只关注与目标直接相关的部分
5. 根据目标需要自行判断分析的深度和广度

## 探索命令示例
```bash
# 确定项目的编程语言
loc

# 查看构建文件和依赖
find . -name "requirements.txt" -o -name "package.json" -o -name "pom.xml" -o -name "Cargo.toml" -o -name "CMakeLists.txt" -o -name "Makefile" | xargs cat

# 获取项目文件结构（支持所有文件类型）
find . -type f -not -path "*/\\.*" | sort

# 查找可能的入口点（支持所有文件类型）
find . -name "main.*" -o -name "app.*" -o -name "index.*" -o -name "startup.*"

# 分析配置文件（支持所有文件类型）
find . -name "*.json" -o -name "*.yaml" -o -name "*.toml" -o -name "*.ini" -o -name "*.conf" -o -name "*.xml"

# 查找核心模块（支持所有文件类型）
find . -name "core.*" -o -name "*core*" -o -name "main.*" -o -name "api.*" -o -name "service.*"
```

## 分析工具使用
- 使用`file_analyzer`分析关键文件结构和功能
- 使用`find_symbol`定位和分析重要符号和函数
- 使用`function_analyzer`深入理解复杂函数的实现
- 使用`find_caller`追踪函数调用关系和依赖

## 分析输出要求
- 直接回应分析目标的关键问题
- 提供与目标相关的深入洞察
- 分析内容应直接服务于分析目标
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
- 以清晰的Markdown格式呈现，简洁明了

在分析中保持灵活性，避免固定思维模式。你的任务不是提供全面的项目概览，而是直接解决分析目标中提出的具体问题。""" 
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
                platform=PlatformRegistry().get_thinking_platform(),
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
1. 在一切分析开始前，先确定项目的主要编程语言和技术栈
2. 理解分析目标，确定你需要寻找什么信息
3. 灵活采用适合目标的分析方法，不受预设分析框架的限制
4. 有选择地探索项目，只关注与目标直接相关的部分
5. 根据目标需要自行判断分析的深度和广度
6. 保证分析的完整性，收集充分的信息后再得出结论，避免基于部分信息做出不完整或错误的判断
7. 查阅项目根目录和主要目录中的README文件、文档文件夹和注释，这些通常包含重要的架构信息、设计原理和使用指南

## 分析步骤
以下步骤应根据具体分析目标灵活应用，可以根据目标相关性跳过或简化某些步骤：

1. **确定项目的编程语言和技术栈**:
   - 统计各类文件数量和分布
   - 检查项目的构建和配置文件
   - 确定使用的主要框架和依赖
   - 如果分析目标不涉及技术栈评估，可简化此步骤

2. **梳理项目结构**:
   - 识别项目的主要目录结构和命名规范
   - 查找并阅读项目中的README.md、docs/目录或其他文档文件
   - 确定项目的模块划分方式
   - 如果分析目标只关注特定模块，可只分析相关部分

3. **定位核心组件**:
   - 根据分析目标找出最相关的文件和目录
   - 识别关键的接口、类和函数
   - 确定组件间的交互方式和依赖关系
   - 如果目标明确指定了组件，可直接跳到该组件分析

4. **分析入口点和执行流程**:
   - 找出项目的入口文件或主要执行脚本
   - 了解主要功能的执行路径
   - 分析初始化和配置加载过程
   - 如果分析目标不涉及执行流程，可跳过此步骤

5. **研究核心实现**:
   - 深入分析与分析目标相关的关键代码
   - 分析关键算法和业务逻辑的实现方式
   - 根据分析目标调整分析深度

6. **总结并提供见解**:
   - 基于分析形成对项目的整体理解
   - 提供与分析目标直接相关的关键发现
   - 做出有建设性的评价和建议

记住：始终将分析目标作为分析过程的指导原则，不必为了完整性而执行与目标无关的步骤。

## 分析工具使用指南

### 工具选择策略
- 自顶向下分析：先了解整体结构，再深入细节
- 目标导向选择：根据分析目标选择最适合的工具
- 信息完备原则：确保收集足够信息后再做结论

### execute_shell
- **用途**：执行系统命令获取项目信息
- **典型用法**：
  - 统计特定类型文件数量
  - 查找特定模式的代码
  - 列出目录内容和结构
- **使用时机**：需要快速获取项目文件统计或查找特定模式

### read_code
- **用途**：读取文件内容进行分析
- **典型用法**：读取配置文件、入口文件、核心模块
- **使用时机**：需要详细了解文件内容时

### find_symbol
- **用途**：查找符号的定义和使用位置
- **典型用法**：查找核心类或全局配置的使用情况
- **使用时机**：需要了解某个重要组件的作用范围

### function_analyzer
- **用途**：深入分析函数实现细节
- **典型用法**：分析项目中的关键功能实现
- **使用时机**：对函数的具体实现细节感兴趣时

### find_caller
- **用途**：查找调用特定函数的位置
- **典型用法**：分析核心功能的使用模式
- **使用时机**：需要了解某个函数如何被项目中不同部分使用

### file_analyzer
- **用途**：分析单个文件的结构和功能
- **典型用法**：分析核心模块文件或复杂实现
- **使用时机**：需要深入理解某个关键文件的结构和功能

### 工具协同使用模式
1. **发现-验证模式**：
   - 发现可能的关键文件
   - 验证其内容是否相关
   - 深入分析确认的关键文件

2. **跟踪-分析模式**：
   - 定位重要组件
   - 跟踪其使用方式
   - 分析关键调用点

3. **自顶向下分析模式**：
   - 先读取项目文档和配置文件
   - 分析入口点文件
   - 逐层深入分析被调用的模块和功能

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
- 确保全面收集相关信息后再形成结论，不要基于不完整的数据提前下结论
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
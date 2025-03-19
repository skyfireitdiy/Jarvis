from typing import Dict, Any, List
import os

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class ProjectAnalyzerTool:
    """
    项目分析工具
    使用agent分析项目结构、入口点、模块划分等信息
    """
    
    name = "project_analyzer"
    description = "分析项目结构、入口点、模块划分等信息，提供项目概览"
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
            "depth": {
                "type": "integer",
                "description": "项目分析深度（可选，0表示无限制）",
                "default": 0
            },
            "analysis_focus": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["structure", "entry_points", "dependencies", "architecture", "all"]
                },
                "description": "分析重点（可选，默认为all）",
                "default": ["all"]
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
            depth = args.get("depth", 0)
            analysis_focus = args.get("analysis_focus", ["all"])
            
            # 创建agent的system prompt
            system_prompt = self._create_system_prompt(
                root_dir, focus_dirs, exclude_dirs, depth, analysis_focus
            )
            
            # 创建agent的summary prompt
            summary_prompt = self._create_summary_prompt(root_dir)
            
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
                "file_analyzer"
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
                             exclude_dirs: List[str], depth: int, 
                             analysis_focus: List[str]) -> str:
        """
        创建Agent的system prompt
        
        Args:
            root_dir: 项目根目录
            focus_dirs: 重点分析的目录列表
            exclude_dirs: 排除的目录列表
            depth: 分析深度
            analysis_focus: 分析重点
            
        Returns:
            系统提示文本
        """
        focus_dirs_str = ", ".join(focus_dirs) if focus_dirs else "整个项目"
        exclude_dirs_str = ", ".join(exclude_dirs) if exclude_dirs else "无"
        depth_str = "无限制" if depth <= 0 else f"{depth}级"
        
        focus_list = []
        if "all" in analysis_focus:
            focus_list = ["项目结构", "入口点", "依赖关系", "架构设计"]
        else:
            if "structure" in analysis_focus: focus_list.append("项目结构")
            if "entry_points" in analysis_focus: focus_list.append("入口点")
            if "dependencies" in analysis_focus: focus_list.append("依赖关系")
            if "architecture" in analysis_focus: focus_list.append("架构设计")
        
        focus_str = ", ".join(focus_list)
        
        return f"""你是一名经验丰富的代码架构分析专家，擅长从项目结构、代码组织和依赖关系中提取关键信息，形成项目的全面概览。

## 当前任务
对位于 `{root_dir}` 的项目进行系统分析，重点分析{focus_str}，生成一份详细的项目概览报告。

## 分析参数
- 项目根目录: {root_dir}
- 重点分析目录: {focus_dirs_str}
- 排除目录: {exclude_dirs_str}
- 分析深度: {depth_str}
- 分析重点: {focus_str}

## 分析流程
请按照以下步骤分析项目:

1. **项目概况识别**
   - 识别项目类型和主要用途
   - 确定项目使用的编程语言和框架
   - 查找项目文档、README和配置文件以获取基本信息

2. **项目结构分析**
   - 分析目录结构和文件组织
   - 识别核心模块和组件
   - 确定代码组织模式(MVC, MVVM等)

3. **入口点分析**
   - 识别主要入口文件(如main.py, index.js等)
   - 分析应用启动流程
   - 确定关键初始化逻辑

4. **模块划分与依赖分析**
   - 识别主要模块及其职责
   - 分析模块间的依赖关系
   - 识别核心服务和关键组件

5. **架构模式识别**
   - 识别使用的架构模式(微服务、单体等)
   - 分析设计模式的应用
   - 确定系统边界和接口

6. **关键文件深度分析**
   - 识别项目中最重要的核心文件
   - 对这些文件进行深入分析，了解其结构和实现
   - 评估这些关键文件的代码质量和最佳实践遵循情况

7. **数据流分析**
   - 追踪关键数据流路径
   - 识别数据模型和存储方式
   - 分析用户输入处理和输出生成

## 工具使用建议
- 使用 `execute_shell` 执行命令:
  ```
  # 列出项目目录结构
  find . -type f -not -path "*/\\.*" | sort
  
  # 查找可能的入口点
  find . -name "main.*" -o -name "app.*" -o -name "index.*"
  
  # 分析依赖关系(Python项目)
  find . -name "requirements.txt" -o -name "setup.py" | xargs cat
  
  # 分析代码统计
  find . -type f -name "*.py" | wc -l
  ```
  
- 使用 `read_code` 读取关键文件:
  ```
  # 读取README或配置文件
  read_code {{
    "files": [
      {{
        "path": "README.md",
        "start_line": 1,
        "end_line": -1
      }}
    ]
  }}
  ```

- 使用 `find_symbol` 查找关键符号的引用和定义:
  ```
  # 查找核心类或关键函数
  find_symbol {{
    "symbol": "核心类或函数名称",
    "root_dir": ".",
    "file_extensions": [".py"],  # 根据项目语言调整
    "exclude_dirs": ["__pycache__", "tests"]
  }}
  ```

- 使用 `function_analyzer` 分析核心函数实现:
  ```
  # 分析入口函数或核心方法
  function_analyzer {{
    "function_name": "main函数或核心方法名",
    "file_path": "找到的文件路径",
    "root_dir": ".",
    "analysis_depth": 1
  }}
  ```

- 使用 `find_caller` 查找函数调用关系:
  ```
  # 查找谁调用了某个核心函数
  find_caller {{
    "function_name": "关键函数名称",
    "root_dir": ".",
    "file_extensions": [".py"]
  }}
  ```

- 使用 `file_analyzer` 深入分析关键文件:
  ```
  # 分析项目中的核心文件
  file_analyzer {{
    "file_path": "关键文件路径",
    "root_dir": ".",
    "analysis_focus": ["structure", "implementation", "dependencies"],
    "include_metrics": true
  }}
  ```

分析完成后，请提供一份全面的项目概览报告，突出项目的关键特性、架构设计和组织结构。
"""

    def _create_summary_prompt(self, root_dir: str) -> str:
        """
        创建Agent的summary prompt
        
        Args:
            root_dir: 项目根目录
            
        Returns:
            总结提示文本
        """
        return f"""请提供位于 `{root_dir}` 的项目的完整分析报告。报告应包含以下部分:

# 项目分析报告

## 项目概述
- 项目名称和用途
- 使用的主要编程语言和框架
- 项目领域和目标用户
- 项目规模和复杂度评估

## 项目结构
- 目录组织和文件布局
- 核心目录及其用途
- 模块划分和职责分配
- 代码组织模式分析

## 入口点和启动流程
- 主要入口文件及其位置
- 应用初始化和启动逻辑
- 配置管理和环境设置
- 命令行参数或启动选项

## 核心模块和组件
- 关键模块列表及其功能
- 核心服务和组件
- 模块间的交互方式
- 重要的设计模式应用

## 关键文件分析
- 项目中最重要的文件清单
- 每个关键文件的主要职责和结构
- 关键文件的实现质量评估
- 关键文件中的潜在问题和优化机会

## 代码分析深度
- 关键函数及其实现分析
- 核心符号在代码库中的引用情况
- 重要函数的调用层级和关系
- 代码重用和抽象模式

## 依赖关系
- 外部依赖概览
- 内部模块依赖图
- 关键第三方库的使用
- 依赖管理机制

## 架构特点
- 整体架构风格(微服务/单体等)
- 关键架构决策
- 可扩展性和可维护性分析
- 潜在的架构挑战

## 数据处理
- 数据模型和存储方式
- 数据流路径
- 状态管理策略
- API和接口设计

## 项目亮点和特色
- 技术上的创新点
- 优秀的设计决策
- 代码质量和最佳实践
- 潜在的改进空间

请确保报告内容全面且深入，使读者能够快速理解项目的整体结构和关键组件。针对项目的特点，可以适当调整报告结构，突出最重要的部分。
""" 
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
            "analysis_focus": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["structure", "implementation", "quality", "dependencies", "all"]
                },
                "description": "分析重点（可选，默认为all）",
                "default": ["all"]
            },
            "include_metrics": {
                "type": "boolean",
                "description": "是否包含代码指标分析（如复杂度、行数等）",
                "default": True
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
            analysis_focus = args.get("analysis_focus", ["all"])
            include_metrics = args.get("include_metrics", True)
            
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
                rel_file_path, file_name, file_ext, root_dir, analysis_focus, include_metrics
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
                             root_dir: str, analysis_focus: list, include_metrics: bool) -> str:
        """
        创建Agent的system prompt
        
        Args:
            file_path: 文件相对路径
            file_name: 文件名
            file_ext: 文件扩展名
            root_dir: 项目根目录
            analysis_focus: 分析重点
            include_metrics: 是否包含代码指标
            
        Returns:
            系统提示文本
        """
        # 根据文件扩展名确定语言
        language_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.c': 'C',
            '.cpp': 'C++',
            '.cs': 'C#',
            '.go': 'Go',
            '.rs': 'Rust',
            '.php': 'PHP',
            '.rb': 'Ruby',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.sh': 'Shell',
            '.html': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.json': 'JSON',
            '.xml': 'XML',
            '.yaml': 'YAML',
            '.md': 'Markdown'
        }
        
        language = language_map.get(file_ext, '未知')
        
        focus_list = []
        if "all" in analysis_focus:
            focus_list = ["文件结构", "实现细节", "代码质量", "依赖关系"]
        else:
            if "structure" in analysis_focus: focus_list.append("文件结构")
            if "implementation" in analysis_focus: focus_list.append("实现细节")
            if "quality" in analysis_focus: focus_list.append("代码质量")
            if "dependencies" in analysis_focus: focus_list.append("依赖关系")
        
        focus_str = ", ".join(focus_list)
        metrics_str = "包含代码指标分析" if include_metrics else "不包含代码指标分析"
        
        return f"""你是一名代码分析专家，擅长深入分析单个源代码文件，提取关键信息并评估代码质量。

## 当前任务
对位于 `{root_dir}` 项目中的文件 `{file_path}` 进行深入分析，重点关注{focus_str}，生成一份详细的单文件分析报告。

## 分析参数
- 文件路径: {file_path}
- 文件名: {file_name}
- 编程语言: {language}
- 项目根目录: {root_dir}
- 分析重点: {focus_str}
- 代码指标: {metrics_str}

## 分析流程
请按照以下步骤分析该文件:

1. **文件概况识别**
   - 确定文件的主要用途和职责
   - 识别文件所属的模块或组件
   - 确定文件的抽象级别和重要性

2. **文件结构分析**
   - 识别主要的类、函数、方法或其他结构元素
   - 分析这些元素之间的关系和组织方式
   - 评估结构的清晰度和组织合理性

3. **实现细节分析**
   - 检查关键算法和实现思路
   - 评估代码的可读性和可维护性
   - 识别潜在的复杂度热点或性能隐患

4. **依赖关系分析**
   - 识别文件导入/引用的外部依赖
   - 分析文件内部元素之间的依赖关系
   - 评估依赖管理的合理性和潜在问题

5. **代码质量评估**
   - 代码风格和一致性
   - 错误处理和边界情况考虑
   - 代码重复性和抽象适当性
   - 注释和文档完整性

6. **${language}最佳实践遵循情况**
   - 识别是否遵循${language}特定的最佳实践
   - 评估是否利用了语言特性
   - 检查是否存在反模式

## 工具使用建议
- 使用 `read_code` 读取文件内容:
  ```
  # 读取整个文件
  read_code {{
    "files": [
      {{
        "path": "{file_path}",
        "start_line": 1,
        "end_line": -1
      }}
    ]
  }}
  ```
  
- 使用 `execute_shell` 获取文件信息:
  ```
  # 获取文件行数和复杂度
  wc -l {file_path}
  
  # 查找导入/依赖语句
  grep -n "import\\|require\\|include" {file_path}
  ```

- 使用 `find_symbol` 查找文件中定义的符号在项目中的引用:
  ```
  # 查找文件中定义的核心类或函数的引用
  find_symbol {{
    "symbol": "核心类或函数名称",
    "root_dir": ".",
    "file_extensions": ["{file_ext}"]
  }}
  ```

- 使用 `function_analyzer` 分析文件中的关键函数:
  ```
  # 分析文件中的主要函数
  function_analyzer {{
    "function_name": "关键函数名称",
    "file_path": "{file_path}",
    "root_dir": ".",
    "analysis_depth": 1
  }}
  ```

分析完成后，请提供一份全面的单文件分析报告，突出文件的主要职责、关键结构、实现特点和代码质量评估。
"""

    def _create_summary_prompt(self, file_path: str, file_name: str) -> str:
        """
        创建Agent的summary prompt
        
        Args:
            file_path: 文件路径
            file_name: 文件名
            
        Returns:
            总结提示文本
        """
        return f"""请提供对文件 `{file_path}` 的完整分析报告。报告应包含以下部分:

# 文件分析报告: `{file_name}`

## 文件概述
- 文件的主要用途和职责
- 所属模块/组件
- 抽象级别和复杂度评估
- 在项目中的重要性

## 结构组织
- 主要类/函数/方法列表及其用途
- 文件的组织逻辑和结构模式
- 主要部分之间的关系
- 代码组织评估

## 关键实现分析
- 核心算法和实现逻辑
- 代码流程和控制结构
- 重要数据结构和状态管理
- 特殊技术或语言特性的使用

## 依赖分析
- 外部导入/依赖列表
- 内部组件间的依赖关系
- 依赖管理评估
- 潜在的依赖问题

## 代码质量评估
- 可读性和可维护性
- 错误处理完备性
- 命名规范和一致性
- 注释和文档质量
- 潜在的代码味道和问题

## 复杂度和指标
- 代码行数统计
- 循环复杂度评估
- 函数/方法长度分析
- 嵌套深度分析

## 最佳实践符合度
- 语言特定最佳实践的遵循情况
- 设计模式的使用
- 反模式的存在

## 改进建议
- 代码质量改进机会
- 结构优化建议
- 性能优化点
- 可维护性提升建议

请确保报告全面且深入，既关注技术细节，也提供高层次的质量评估，使读者能够全面了解该文件的结构、质量和在项目中的作用。
""" 
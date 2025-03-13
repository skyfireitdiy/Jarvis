from typing import Dict, Any
import os
from jarvis.jarvis_rag.main import RAGTool as RAGCore
from jarvis.jarvis_utils.config import dont_use_local_model
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class RAGTool:
    name = "rag"
    description = "基于文档目录进行问答，支持多种文档格式（txt、pdf、docx等）"
    parameters = {
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "文档目录路径，支持相对路径和绝对路径"
            },
            "question": {
                "type": "string",
                "description": "要询问的问题"
            },
            "rebuild_index": {
                "type": "boolean",
                "description": "是否重建索引",
                "default": False
            }
        },
        "required": ["dir", "question"]
    }

    @staticmethod
    def check() -> bool:
        return not dont_use_local_model()

    def __init__(self):
        """Initialize RAG tool"""
        self.rag_instances = {}  # Cache RAG instances for different directories

    def _get_rag_instance(self, dir_path: str) -> RAGCore:
        """Get or create RAG instance
        
        Args:
            dir_path: The absolute path of the document directory
            
        Returns:
            RAGCore: RAG instance
        """
        if dir_path not in self.rag_instances:
            self.rag_instances[dir_path] = RAGCore(dir_path)
        return self.rag_instances[dir_path]

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行文档问答
        
        Args:
            args: 包含参数的字典
                - dir: 文档目录路径
                - question: 要询问的问题
                - rebuild_index: 是否重建索引
                
        Returns:
            Dict[str, Any]: 执行结果，包含以下字段：
                - success: 布尔值，表示操作是否成功
                - stdout: 如果成功，包含问题的答案
                - stderr: 如果失败，包含错误信息
        """
        try:
            # 获取参数
            dir_path = os.path.expanduser(args["dir"])
            dir_path = os.path.abspath(dir_path)
            question = args["question"]
            rebuild_index = args.get("rebuild_index", False)
            
            # 检查目录是否存在
            if not os.path.exists(dir_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Directory does not exist: {dir_path}"
                }
                
            # 检查路径是否为目录
            if not os.path.isdir(dir_path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"The path is not a directory: {dir_path}"
                }
                
            # 获取RAG实例
            rag = self._get_rag_instance(dir_path)
            
            # 如果需要重建索引或索引不存在
            if rebuild_index or not rag.is_index_built():
                PrettyOutput.print("正在构建文档索引...", OutputType.INFO)
                rag.build_index(dir_path)
            
            # 执行问答
            PrettyOutput.print(f"问题: {question}", OutputType.INFO)
            response = rag.ask(question)
            
            # 处理未找到相关文档的情况
            if response is None:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to get answer, possibly no relevant documents found"
                }
                
            # 返回成功响应
            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }
            
        except Exception as e:
            # 处理任何意外错误
            PrettyOutput.print(f"文档问答失败：{str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution failed: {str(e)}"
            }

def main():
    """Run the tool directly from the command line"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Document question and answer tool')
    parser.add_argument('--dir', required=True, help='Document directory path')
    parser.add_argument('--question', required=True, help='The question to ask')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild index')
    args = parser.parse_args()
    
    tool = RAGTool()
    result = tool.execute({
        "dir": args.dir,
        "question": args.question,
        "rebuild_index": args.rebuild
    })
    
    if result["success"]:
        PrettyOutput.print(f"{result['stdout']}", OutputType.INFO, lang="markdown")
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)

if __name__ == "__main__":
    main()
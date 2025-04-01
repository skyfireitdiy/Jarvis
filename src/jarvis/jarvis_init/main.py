from typing import Any, Tuple
import subprocess
from jarvis.jarvis_utils.embedding import (
    get_context_token_count,
    load_tokenizer
)
from jarvis.jarvis_utils.output import PrettyOutput, OutputType

def init_models() -> Tuple[Any, Any, Any, Any]:
    """
    初始化所需的模型和分词器。
    
    返回：
        Tuple[Any, Any, Any, Any]: (embedding_model, rerank_model, rerank_tokenizer, tokenizer)
    """
    try:
        
        # 加载GPT2分词器
        PrettyOutput.print("正在加载GPT2分词器...", OutputType.INFO)
        tokenizer = load_tokenizer()
        
        # 测试token计算
        test_text = "这是一个测试文本，用于验证token计算功能。"
        token_count = get_context_token_count(test_text)
        PrettyOutput.print(f"Token计算测试成功，测试文本token数: {token_count}", OutputType.SUCCESS)
        
        return embedding_model, rerank_model, rerank_tokenizer, tokenizer
        
    except Exception as e:
        PrettyOutput.print(f"模型加载失败: {str(e)}", OutputType.ERROR)
        raise

def install_playwright():
    """安装Playwright及其依赖。"""
    try:
        PrettyOutput.print("正在安装Playwright...", OutputType.INFO)
        subprocess.run(["playwright", "install", "chromium"], check=True)
        PrettyOutput.print("Playwright安装成功", OutputType.SUCCESS)
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(f"Playwright安装失败: {str(e)}", OutputType.ERROR)
        raise
    except Exception as e:
        PrettyOutput.print(f"安装过程中发生错误: {str(e)}", OutputType.ERROR)
        raise

def main():
    """主函数，初始化所有必要的组件。"""
    try:
        # 初始化模型
        init_models()
        
        # 安装Playwright
        install_playwright()
        
        PrettyOutput.print("所有组件初始化完成", OutputType.SUCCESS)
        
    except Exception as e:
        PrettyOutput.print(f"初始化失败: {str(e)}", OutputType.ERROR)
        raise

if __name__ == "__main__":
    main()

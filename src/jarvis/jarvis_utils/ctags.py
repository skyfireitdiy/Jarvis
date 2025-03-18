import subprocess
from pathlib import Path
from typing import Optional, Tuple
from functools import lru_cache

@lru_cache(maxsize=128)
def get_symbol_location(symbol: str, source_dir: str) -> Optional[Tuple[str, int]]:
    """
    使用ctags获取指定符号的位置信息
    
    Args:
        symbol (str): 要查找的符号名称
        source_dir (str): 源代码目录路径
    
    Returns:
        Optional[Tuple[str, int]]: 返回包含文件路径和行号的元组，如果未找到则返回None
    """
    # 生成tags文件
    tags_file = Path(source_dir) / 'tags'
    try:
        subprocess.run(
            ['ctags', '-R', '--python-kinds=-iv', '--fields=+n', '-f', str(tags_file), source_dir],
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to generate tags: {e}")

    # 解析tags文件查找符号
    with open(tags_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith(symbol + '\t'):
                parts = line.split('\t')
                if len(parts) >= 4:
                    file_path = parts[1]
                    line_number = int(parts[3].split(';')[0])
                    return (file_path, line_number)
    
    return None

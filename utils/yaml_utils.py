import re
import yaml
from typing import Optional, Dict, Any

def extract_yaml_from_response(response: str) -> Optional[Dict[str, Any]]:
    """从响应中提取YAML对象"""
    # 1. 尝试从代码块中提取
    code_block_pattern = r"```(?:yaml)?\s*([\s\S]*?)\s*```"
    matches = re.findall(code_block_pattern, response)
    
    for match in matches:
        try:
            yaml_obj = yaml.safe_load(match)
            if isinstance(yaml_obj, dict):
                return yaml_obj
        except yaml.YAMLError:
            continue
    
    # 2. 尝试直接解析整个响应
    try:
        yaml_obj = yaml.safe_load(response)
        if isinstance(yaml_obj, dict):
            return yaml_obj
    except yaml.YAMLError:
        pass
    
    return None 
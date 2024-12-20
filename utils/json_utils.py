import json
import re
from typing import Dict, Any, Optional

def extract_json_from_response(response: str) -> Dict[str, Any]:
    """Extract JSON object from LLM response"""
    # Find JSON between ```json and ``` markers
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON from code block: {str(e)}")
    
    # If no code block found or parsing failed, try to find bare JSON object
    json_match = re.search(r'(\{.*\})', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError as e:
            print(f"Failed to parse bare JSON: {str(e)}")
    
    # If all attempts fail, return empty dict
    return {}
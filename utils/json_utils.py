import re
import json
from typing import Dict, Any, Optional

def extract_json_from_response(response: str) -> Dict[str, Any]:
    """Extract JSON object from a string that may contain other text
    
    Args:
        response: String that may contain a JSON object
        
    Returns:
        Extracted JSON object as dict
    """
    # Try to find JSON-like content between curly braces
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    
    if json_match:
        try:
            # Parse the matched content
            json_str = json_match.group(0)
            return json.loads(json_str)
        except json.JSONDecodeError:
            # If parsing fails, return empty dict
            return {}
    
    # If no JSON-like content found, return empty dict
    return {} 
import json
import re
from typing import Dict, Any, Optional

def extract_json_from_response(response: str) -> Dict[str, Any]:
    """Extract JSON object from LLM response"""
    try:
        # Try to parse the entire response as JSON first
        return json.loads(response)
    except json.JSONDecodeError:
        # If that fails, try to find JSON object in the response
        try:
            # Find the first { and last }
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                
                # Clean up the JSON string
                json_str = json_str.replace('\n', ' ')
                
                # Fix common syntax issues
                json_str = json_str.replace(' && ', ', ')  # Replace && with comma
                json_str = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_str)  # Quote unquoted keys
                json_str = re.sub(r':\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(,|})', r': "\1"\2', json_str)  # Quote unquoted values
                json_str = re.sub(r'(?<!\\)"([^"]*?)":', r'"\1":', json_str)  # Fix already quoted keys
                json_str = re.sub(r'(?<!\\)"([^"]*?)"(?=,|})', r'"\1"', json_str)  # Fix already quoted values
                json_str = re.sub(r'#.*$', '', json_str, flags=re.MULTILINE)  # Remove comments
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)  # Remove trailing commas
                json_str = re.sub(r',\s*,', ',', json_str)  # Remove duplicate commas
                
                # Try to parse the cleaned JSON
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    print(f"Failed to parse JSON after cleaning: {str(e)}")
                    print(f"Cleaned JSON string: {json_str}")
                    return {}
            else:
                raise ValueError("No JSON object found in response")
        except Exception as e:
            print(f"Error extracting JSON: {str(e)}")
            return {} 
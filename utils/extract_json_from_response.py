import json
import re

def extract_json_from_response(response: str) -> dict:
    """Extract JSON from LLM response"""
    try:
        # Try to find JSON block between ```
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find first occurrence of { ... }
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                return {}
        
        # Clean up the JSON string
        json_str = re.sub(r'[\n\r]', ' ', json_str)  # Remove newlines
        json_str = re.sub(r'\s+', ' ', json_str)     # Normalize whitespace
        json_str = re.sub(r',\s*}', '}', json_str)   # Remove trailing commas
        
        # Parse JSON
        return json.loads(json_str)
    except Exception as e:
        print(f"Error extracting JSON: {e}")
        return {} 
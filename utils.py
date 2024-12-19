import json
import re
from colorama import Fore, Style
from typing import Dict, Any, List, Union

def extract_json_from_response(response: str) -> Dict[str, Any]:
    """Extract JSON object from LLM response"""
    try:
        # Try to find JSON-like content between triple backticks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find content between single backticks
            json_match = re.search(r'`(\{.*?\}|\[.*?\])`', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find bare JSON object or array
                json_match = re.search(r'(\{.*?\}|\[.*?\])', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    return {"error": "No JSON content found"}

        # Parse the JSON content
        data = json.loads(json_str)
        
        # If it's a list with one object, return that object
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            return data[0]
        # If it's a list with multiple objects or not a list at all, wrap it
        elif isinstance(data, list):
            return {"error": "Expected single JSON object, got array"}
        # If it's already a dict, return it
        elif isinstance(data, dict):
            return data
        else:
            return {"error": "Invalid JSON structure"}
            
    except json.JSONDecodeError as e:
        return {"error": f"JSON decode error: {str(e)}"}
    except Exception as e:
        return {"error": f"Error extracting JSON: {str(e)}"}

def ask_user_confirmation(message: str) -> bool:
    """Ask user for execution confirmation"""
    while True:
        response = input(f"{Fore.YELLOW}{message} (y/n): {Style.RESET_ALL}").lower()
        if response in ['y', 'yes']:
            return True
        if response in ['n', 'no']:
            return False
        print(f"{Fore.RED}Please enter y or n{Style.RESET_ALL}") 

def extract_potential_jsons(s: str) -> List[str]:
    """Extract potential JSON strings from text"""
    potential_jsons = []
    i = 0
    while i < len(s):
        if s[i] == '{' or s[i] == '[':
            end = find_matching_bracket(s, i)
            if end != -1:
                potential_jsons.append(s[i:end + 1])
                i = end
        i += 1
    return potential_jsons

def find_matching_bracket(s: str, start: int) -> int:
    """Find matching closing bracket position"""
    stack = []
    brackets = {'{': '}', '[': ']'}
    closing_brackets = set(brackets.values())
    
    for i in range(start, len(s)):
        char = s[i]
        if char in brackets:  # Opening bracket
            stack.append(char)
        elif char in closing_brackets:  # Closing bracket
            if not stack:  # No matching opening bracket
                return -1
            if char != brackets[stack[-1]]:  # Bracket type mismatch
                return -1
            stack.pop()
            if not stack:  # Found complete match
                return i
    return -1  # No matching closing bracket found
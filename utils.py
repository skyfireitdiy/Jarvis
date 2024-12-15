import json
import re
from colorama import Fore, Style
from typing import Dict, Any

def extract_json_from_response(response: str) -> Dict[str, Any]:
    """Extract JSON content from model response using bracket matching"""
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

    def extract_potential_jsons(s: str) -> list[str]:
        """Extract all possible JSON strings"""
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

    # First try to parse the entire response
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try to extract from markdown code blocks
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    code_blocks = re.findall(code_block_pattern, response)
    for block in code_blocks:
        # Extract all possible JSONs from code blocks
        potential_jsons = extract_potential_jsons(block)
        for json_str in potential_jsons:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue

    # Extract from entire response
    potential_jsons = extract_potential_jsons(response)
    for json_str in potential_jsons:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            continue

    # Return error if no valid JSON found
    return {
        "error": "Failed to extract valid JSON from response",
        "original_response": response
    }

def ask_user_confirmation(message: str) -> bool:
    """Ask user for execution confirmation"""
    while True:
        response = input(f"{Fore.YELLOW}{message} (y/n): {Style.RESET_ALL}").lower()
        if response in ['y', 'yes']:
            return True
        if response in ['n', 'no']:
            return False
        print(f"{Fore.RED}Please enter y or n{Style.RESET_ALL}") 
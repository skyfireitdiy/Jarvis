import re
import yaml
import logging
from typing import Optional, Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

def extract_yaml_from_response(response: str) -> Optional[Dict[str, Any]]:
    """Extract and parse YAML content from LLM response"""
    try:
        # Try to find YAML content between code blocks
        if "```yaml" in response:
            # Extract content between ```yaml and ```
            start = response.find("```yaml") + 7
            end = response.find("```", start)
            yaml_content = response[start:end].strip()
        elif "```" in response:
            # Try without yaml tag
            start = response.find("```") + 3
            end = response.find("```", start)
            yaml_content = response[start:end].strip()
        else:
            # Try to parse the entire response as YAML
            yaml_content = response.strip()
        
        # Parse YAML content
        if yaml_content:
            result = yaml.safe_load(yaml_content)
            if isinstance(result, dict):
                # Clean up tool names if present
                if "next_steps" in result and isinstance(result["next_steps"], list):
                    for step in result["next_steps"]:
                        if isinstance(step, dict) and "tool" in step:
                            # Remove any parenthetical descriptions from tool name
                            tool_name = step["tool"]
                            if isinstance(tool_name, str):
                                step["tool"] = tool_name.split(" (")[0].strip()
            return result
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to parse YAML: {str(e)}")
        logger.debug(f"Raw response:\n{response}")
        return None 
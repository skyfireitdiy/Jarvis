import os
from typing import Dict, Any
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.utils import OutputType, PrettyOutput

class DeepThinkingTool:
    """Tool for deep thinking about user requirements using thinking platform."""
    
    name = "deep_thinking"
    description = "Analyze and think deeply about user requirements"
    parameters = {
        "requirement": "The requirement or question to think about",
        "mode": {
            "type": "string",
            "description": "Thinking mode: analysis/solution/critique",
            "enum": ["analysis", "solution", "critique"],
            "default": "analysis"
        }
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            requirement = args.get("requirement", "")
            mode = args.get("mode", "analysis")
            
            if not requirement:
                return {
                    "success": False,
                    "stderr": "Requirement must be provided",
                    "stdout": ""
                }
            
            # Get thinking platform
            platform = PlatformRegistry().get_thinking_platform()
            
            # Build prompt based on mode
            if mode == "analysis":
                prompt = f"""Please analyze this requirement deeply. Consider:

1. Core Objectives:
   - What is the fundamental goal?
   - What are the key requirements?
   - What are the implicit needs?

2. Scope Analysis:
   - What is included/excluded?
   - What are the boundaries?
   - What are potential edge cases?

3. Challenges:
   - What are the technical challenges?
   - What are potential risks?
   - What needs special attention?

4. Dependencies:
   - What are the prerequisites?
   - What systems will be affected?
   - What integrations are needed?

Requirement to analyze:
{requirement}

Please provide a structured analysis."""

            elif mode == "solution":
                prompt = f"""Please think deeply about potential solutions. Consider:

1. Solution Approaches:
   - What are possible approaches?
   - What are the pros/cons of each?
   - What is the recommended approach?

2. Implementation Strategy:
   - How should this be implemented?
   - What are the key steps?
   - What is the suggested order?

3. Technical Considerations:
   - What technologies should be used?
   - What patterns would work best?
   - What should be avoided?

4. Risk Mitigation:
   - How to handle potential issues?
   - What safeguards are needed?
   - What should be tested carefully?

Requirement to solve:
{requirement}

Please provide a structured solution plan."""

            else:  # critique
                prompt = f"""Please critique this requirement carefully. Consider:

1. Clarity:
   - Is it clearly defined?
   - Are there ambiguities?
   - What needs clarification?

2. Completeness:
   - Are all aspects covered?
   - What might be missing?
   - Are edge cases considered?

3. Feasibility:
   - Is it technically feasible?
   - Are there resource constraints?
   - What are potential blockers?

4. Improvements:
   - How could it be better?
   - What should be added/removed?
   - What alternatives exist?

Requirement to critique:
{requirement}

Please provide a structured critique."""

            # Get thinking result
            result = platform.chat_until_success(prompt)
            
            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Thinking failed: {str(e)}",
                "stdout": ""
            }

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Deep thinking tool')
    parser.add_argument('requirement', help='Requirement to think about')
    parser.add_argument('--mode', choices=['analysis', 'solution', 'critique'],
                      default='analysis', help='Thinking mode')
    
    args = parser.parse_args()
    
    tool = DeepThinkingTool()
    result = tool.execute({
        "requirement": args.requirement,
        "mode": args.mode
    })
    
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)

if __name__ == "__main__":
    main()

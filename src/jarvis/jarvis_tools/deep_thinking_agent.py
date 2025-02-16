import os
from typing import Dict, Any
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import OutputType, PrettyOutput

class DeepThinkingAgentTool:
    """Tool for deep thinking using an agent with thinking platform."""
    
    name = "deep_thinking_agent"
    description = "Use an agent to think deeply about problems and solutions"
    parameters = {
        "question": "The question or problem to think about"
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            question = args.get("question", "")
            if not question:
                return {
                    "success": False,
                    "stderr": "Question must be provided",
                    "stdout": ""
                }
            
            # Initialize tool registry
            tool_registry = ToolRegistry()
            tool_registry.dont_use_tools([
                "deep_thinking_agent"
            ])
            
            # Define system prompt for thinking agent
            system_prompt = """You are a deep thinking agent that carefully analyzes problems and proposes solutions.

THINKING PROCESS:
1. Initial Analysis
   ```
   Thought: Let me first understand the core problem...
   Action: Use deep_thinking with mode=analysis
   Observation: The analysis shows...
   
   Thought: I need more information about...
   Action: Use appropriate tool (search/ask_user/ask_codebase)
   Observation: Found that...
   ```

2. Solution Exploration
   ```
   Thought: Let me explore possible solutions...
   Action: Use deep_thinking with mode=solution
   Observation: The potential solutions are...
   
   Thought: I should validate these approaches...
   Action: Use appropriate tool to verify
   Observation: Verification shows...
   ```

3. Critical Review
   ```
   Thought: Let me critique the proposed solution...
   Action: Use deep_thinking with mode=critique
   Observation: The critique reveals...
   
   Thought: These points need addressing...
   Action: Revise solution based on critique
   Observation: The improved solution...
   ```

4. Final Recommendation
   ```
   Thought: Synthesize all findings...
   Action: Compile final recommendation
   Output: Detailed solution with rationale
   ```

GUIDELINES:
- Use deep_thinking tool for structured analysis
- Validate assumptions with search/ask_user
- Consider multiple perspectives
- Provide evidence for conclusions
- Be thorough but practical
- Focus on actionable recommendations

Please proceed with the analysis and provide a comprehensive response."""
            
            # Create agent with thinking platform
            agent = Agent(
                system_prompt=system_prompt,
                name="DeepThinkingAgent",
                tool_registry=tool_registry,
                platform=PlatformRegistry().get_thinking_platform(),
                auto_complete=True,
                is_sub_agent=True,
                summary_prompt="""Please provide a structured summary of your thinking process and conclusions:

<THINKING_SUMMARY>
Analysis:
[Key findings from analysis]

Solutions:
[Proposed solutions and rationale]

Critique:
[Critical considerations]

Recommendation:
[Final recommendation with justification]
</THINKING_SUMMARY>"""
            )
            
            # Run agent
            result = agent.run(question)
            
            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stderr": f"Deep thinking failed: {str(e)}",
                "stdout": ""
            }

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Deep thinking agent')
    parser.add_argument('question', help='Question or problem to think about')
    
    args = parser.parse_args()
    
    tool = DeepThinkingAgentTool()
    result = tool.execute({"question": args.question})
    
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)

if __name__ == "__main__":
    main()

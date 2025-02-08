from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput


class CodeModifyAgentTool:
    name = "execute_code_modification"
    description = "Execute code modifications according to the provided plan"
    parameters = {
        "type": "object",
        "properties": {
            "modification_plan": {
                "type": "string",
                "description": "Detailed plan for code modifications"
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of files to be modified",
                "default": []
            },
            "code_context": {
                "type": "string",
                "description": "Current code context and structure",
                "default": ""
            },
            "verification_requirements": {
                "type": "string",
                "description": "Requirements for verifying the modifications",
                "default": ""
            }
        },
        "required": ["modification_plan"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute code modifications according to plan"""
        try:
            modification_plan = args["modification_plan"]
            files = args.get("files", [])
            code_context = args.get("code_context", "")
            verification_requirements = args.get("verification_requirements", "")

            PrettyOutput.print("Executing code modifications...", OutputType.INFO)

            # Customize system message for code modification
            system_message = """You are a Code Modification Agent specialized in implementing code changes safely and efficiently.

Your task is to:
1. Follow the modification plan precisely
2. Make incremental changes
3. Verify each modification
4. Maintain code quality
5. Document all changes

Implementation Guidelines:
- Make one change at a time
- Test after each modification
- Keep consistent code style
- Update documentation as needed
- Follow version control best practices

For each modification:
1. PREPARATION
   - Review the specific change
   - Identify affected code sections
   - Plan the implementation

2. IMPLEMENTATION
   - Use code_edit tool for changes
   - Follow coding standards
   - Add/update comments
   - Maintain error handling

3. VERIFICATION
   - Review the changes
   - Run relevant tests
   - Check for side effects
   - Verify requirements

4. VERSION CONTROL
   - Create clear commit message
   - Include change description
   - Reference related issues
   - Use git_commit tool

Error Handling:
- Detect potential issues early
- Roll back failed changes
- Document any problems
- Suggest alternatives if needed

Output Format:
- Status of each modification
- Verification results
- Any issues encountered
- Next steps or recommendations"""

            # Create modification agent
            modification_agent = Agent(
                system_prompt=system_message,
                name="CodeModificationAgent",
                is_sub_agent=True
            )

            # Build comprehensive task description
            task_description = f"""CODE MODIFICATION EXECUTION TASK

MODIFICATION PLAN:
{modification_plan}

"""
            if files:
                task_description += f"""
FILES TO MODIFY:
{', '.join(files)}

"""
            if code_context:
                task_description += f"""
CODE CONTEXT:
{code_context}

"""
            if verification_requirements:
                task_description += f"""
VERIFICATION REQUIREMENTS:
{verification_requirements}
"""

            # Execute modifications
            result = modification_agent.run(task_description)

            return {
                "success": True,
                "stdout": f"Code Modification Results:\n\n{result}",
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"Failed to execute code modifications: {str(e)}"
            }

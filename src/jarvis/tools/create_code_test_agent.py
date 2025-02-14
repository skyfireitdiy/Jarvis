from typing import Dict, Any
from jarvis.agent import Agent
from jarvis.tools.registry import ToolRegistry
import subprocess

class TestAgentTool:
    name = "create_code_test_agent"
    description = "Create testing agent for specific commit analysis"
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Identifier for the test agent"
            },
            "test_scope": {
                "type": "string", 
                "enum": ["unit", "integration", "e2e"],
                "description": "Testing focus area"
            },
            "commit_sha": {
                "type": "string",
                "description": "Commit SHA to analyze"
            }
        },
        "required": ["name", "test_scope", "commit_sha"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute commit-focused testing"""
        try:
            if not self._is_valid_commit(args["commit_sha"]):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Invalid commit SHA: {args['commit_sha']}"
                }

            tool_registry = ToolRegistry()  
            tool_registry.dont_use_tools(["create_code_test_agent"])

            test_agent = Agent(
                system_prompt=self._build_system_prompt(args),
                name=f"TestAgent({args['name']})",
                is_sub_agent=True,
                tool_registry=tool_registry
            )

            result = test_agent.run(
                f"Analyze and test changes in commit {args['commit_sha'].strip()}"
            )

            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Commit testing failed: {str(e)}"
            }

    def _is_valid_commit(self, commit_sha: str) -> bool:
        """Validate commit exists in repository"""
        try:
            cmd = f"git cat-file -t {commit_sha}"
            result = subprocess.run(
                cmd.split(), 
                capture_output=True, 
                text=True,
                check=True
            )
            return "commit" in result.stdout
        except subprocess.CalledProcessError:
            return False

    def _build_system_prompt(self, args: Dict) -> str:
        return """You are a Commit Testing Specialist. Follow this protocol:

【Testing Protocol】
1. Commit Analysis:
   - Analyze code changes in target commit
   - Identify modified components
   - Assess change impact scope

2. Test Strategy:
   - Determine required test types
   - Verify backward compatibility
   - Check interface contracts

3. Test Execution:
   - Execute relevant test suites
   - Compare pre/post-commit behavior
   - Validate cross-component interactions

4. Reporting:
   - List affected modules
   - Risk assessment matrix
   - Performance impact analysis
   - Security implications

【Output Requirements】
- Test coverage analysis
- Behavioral change summary
- Critical issues prioritized
- Actionable recommendations

【Key Principles】
1. Focus on delta changes
2. Maintain test isolation
3. Preserve historical baselines
4. Automate verification steps
5. Document test evidence"""

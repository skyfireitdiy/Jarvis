from typing import Dict, Any

from jarvis.agent import Agent
from jarvis.utils import OutputType, PrettyOutput


class CodeTestAgentTool:
    name = "verify_code_changes"
    description = "Verify and test code modifications to ensure quality and correctness"
    parameters = {
        "type": "object",
        "properties": {
            "modified_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of modified files to test",
                "default": []
            },
            "test_requirements": {
                "type": "string",
                "description": "Specific testing requirements and criteria",
                "default": ""
            },
            "original_functionality": {
                "type": "string",
                "description": "Description of the original functionality to verify",
                "default": ""
            },
            "expected_changes": {
                "type": "string",
                "description": "Expected changes and their impacts",
                "default": ""
            },
            "test_scope": {
                "type": "string",
                "enum": ["unit", "integration", "all"],
                "description": "Scope of testing to perform",
                "default": "all"
            }
        },
        "required": ["modified_files"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute code testing and verification"""
        try:
            modified_files = args["modified_files"]
            test_requirements = args.get("test_requirements", "")
            original_functionality = args.get("original_functionality", "")
            expected_changes = args.get("expected_changes", "")
            test_scope = args.get("test_scope", "all")

            PrettyOutput.print("Starting code verification and testing...", OutputType.INFO)

            # Customize system message for testing
            system_message = """You are a Code Testing Agent specialized in verifying code changes and ensuring quality.

Your task is to:
1. Review modified code thoroughly
2. Execute appropriate tests
3. Verify functionality
4. Check for regressions
5. Document test results

Testing Strategy:
1. CODE REVIEW
   - Check code style
   - Verify documentation
   - Review error handling
   - Assess code structure

2. STATIC ANALYSIS
   - Use code_lint tool if available
   - Check for potential issues
   - Verify type annotations
   - Review dependencies

3. FUNCTIONAL TESTING
   - Unit tests
   - Integration tests
   - Edge cases
   - Error scenarios

4. VERIFICATION STEPS
   - Original functionality preserved
   - New features working
   - No regressions
   - Performance impact

Quality Checks:
- Code standards compliance
- Documentation completeness
- Error handling robustness
- Performance considerations
- Security implications

Test Documentation:
- Test scenarios covered
- Test results
- Issues found
- Recommendations

Output Format:
1. TEST SUMMARY
   - Overall status
   - Critical findings
   - Test coverage

2. DETAILED RESULTS
   - Test case outcomes
   - Verification status
   - Issues identified

3. RECOMMENDATIONS
   - Required fixes
   - Improvements needed
   - Follow-up actions"""

            # Create test agent
            test_agent = Agent(
                system_prompt=system_message,
                name="CodeTestingAgent",
                is_sub_agent=True
            )

            # Build comprehensive test description
            test_description = f"""CODE TESTING TASK

FILES TO TEST:
{', '.join(modified_files)}

TESTING SCOPE:
{test_scope}

"""
            if test_requirements:
                test_description += f"""
TEST REQUIREMENTS:
{test_requirements}

"""
            if original_functionality:
                test_description += f"""
ORIGINAL FUNCTIONALITY:
{original_functionality}

"""
            if expected_changes:
                test_description += f"""
EXPECTED CHANGES:
{expected_changes}
"""

            # Execute tests
            test_results = test_agent.run(test_description)

            return {
                "success": True,
                "stdout": f"Code Testing Results:\n\n{test_results}",
                "stderr": ""
            }

        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "error": f"Failed to execute code tests: {str(e)}"
            }

from typing import Dict, Any, List
from jarvis.agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import PrettyOutput, OutputType, init_env, user_confirm

from jarvis.jarvis_dev.pm import ProductManager
from jarvis.jarvis_dev.ba import BusinessAnalyst
from jarvis.jarvis_dev.tl import TechLead
from jarvis.jarvis_dev.sa import SystemAnalyst
from jarvis.jarvis_dev.dev import Developer
from jarvis.jarvis_dev.qa import QualityAssurance

class DevTeam:
    """Development team with multiple roles"""
    
    def __init__(self):
        """Initialize development team"""
        self.pm = ProductManager()
        self.tl = TechLead()
        self.ba = BusinessAnalyst()
        self.sa = SystemAnalyst() 
        self.dev = Developer()
        self.qa = QualityAssurance()
        
    def handle_requirement(self, requirement: str) -> Dict[str, Any]:
        """Handle development requirement with team collaboration"""
        try:
            while True:  # Main development loop
                # Show stage selection menu
                PrettyOutput.print("\n=== Development Stages ===", OutputType.INFO)
                stages = [
                    "1. Product Manager Analysis",
                    "2. Business Analyst Analysis", 
                    "3. Tech Lead Design",
                    "4. System Analyst Design",
                    "5. Development & QA",
                    "6. Exit"
                ]

                stage_out = '\n'.join(stages)
                PrettyOutput.print(stage_out, OutputType.INFO)
                
                choice = input("\nSelect stage to execute (1-6): ").strip()
                
                if choice == "6":
                    return {"success": False, "error": "Development cancelled by user"}
                
                if choice == "1":
                    # PM Analysis
                    PrettyOutput.section("\n=== Product Manager Analysis ===", OutputType.INFO)
                    pm_result = self.pm.analyze_requirement(requirement)
                    if not pm_result["success"]:
                        return pm_result
                    
                    PrettyOutput.print(pm_result["analysis"], OutputType.INFO)
                    if not user_confirm("Continue to next stage?"):
                        continue
                
                if choice <= "2":
                    # BA Analysis
                    PrettyOutput.section("\n=== Business Analyst Analysis ===", OutputType.INFO)
                    ba_result = self.ba.analyze_business(pm_result["tasks"])
                    if not ba_result["success"]:
                        return ba_result
                    
                    PrettyOutput.print(ba_result["analysis"], OutputType.INFO)
                    if not user_confirm("Continue to next stage?"):
                        continue
                
                if choice <= "3":
                    # TL Design
                    PrettyOutput.section("\n=== Tech Lead Design ===", OutputType.INFO)
                    tl_result = self.tl.design_solution(ba_result["analysis"])
                    if not tl_result["success"]:
                        return tl_result
                    
                    PrettyOutput.print(tl_result["design"], OutputType.INFO)
                    if not user_confirm("Continue to next stage?"):
                        continue
                
                if choice <= "4":
                    # SA Design
                    PrettyOutput.section("\n=== System Analyst Design ===", OutputType.INFO)
                    sa_result = self.sa.design_system(tl_result["design"])
                    if not sa_result["success"]:
                        return sa_result
                    
                    PrettyOutput.print(sa_result["design"], OutputType.INFO)
                    if not user_confirm("Continue to next stage?"):
                        continue
                
                if choice <= "5":
                    # Dev & QA iterations
                    max_iterations = 3
                    iteration = 0
                    
                    while iteration < max_iterations:
                        iteration += 1
                        PrettyOutput.section(f"\n=== Development Iteration {iteration} ===", OutputType.INFO)
                        
                        dev_result = self.dev.implement(sa_result["design"])
                        if not dev_result["success"]:
                            return dev_result
                        
                        PrettyOutput.print(dev_result["implementation"], OutputType.INFO)
                        if not user_confirm("Continue with implementation?"):
                            break
                        
                        PrettyOutput.section("\n=== QA Verification ===", OutputType.INFO)
                        qa_result = self.qa.verify(dev_result["implementation"])
                        if not qa_result["success"]:
                            return qa_result
                        
                        PrettyOutput.print(qa_result["verification"], OutputType.INFO)
                        
                        if "verification" in qa_result and "test_results" in qa_result["verification"]:
                            if self._check_qa_passed(qa_result["verification"]):
                                if user_confirm("QA verification passed. Complete development?"):
                                    return {
                                        "success": True,
                                        "result": {
                                            "requirement": requirement,
                                            "pm_analysis": pm_result,
                                            "ba_analysis": ba_result,
                                            "tl_design": tl_result,
                                            "sa_design": sa_result,
                                            "dev_implementation": dev_result,
                                            "qa_verification": qa_result,
                                            "iterations": iteration
                                        }
                                    }
                        
                        if iteration == max_iterations:
                            if not user_confirm("Max iterations reached. Return to previous stage?"):
                                return {
                                    "success": False,
                                    "error": "Max iterations reached without passing QA"
                                }
                            break
                        
                        if not user_confirm("Start next iteration?"):
                            break
                        
                        sa_result["design"] = self._update_design_with_qa_feedback(
                            sa_result["design"], 
                            qa_result["verification"]
                        )
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Development process failed: {str(e)}"
            }

    def _check_qa_passed(self, verification: Dict) -> bool:
        """Check if QA verification passed"""
        try:
            # Check unit tests
            unit_tests = verification["test_results"]["unit_tests"]
            for suite in unit_tests:
                if suite["failed"] > 0:
                    return False
                
            # Check integration tests    
            integration_tests = verification["test_results"]["integration_tests"]
            for suite in integration_tests:
                for scenario in suite["scenarios"]:
                    if scenario["status"] == "Fail":
                        return False
                        
            # Check critical issues
            if verification["recommendations"]["critical_issues"]:
                return False
                
            return True
            
        except Exception:
            return False
            
    def _update_design_with_qa_feedback(self, design: str, qa_feedback: Dict) -> str:
        """Update design based on QA feedback"""
        try:
            # Create feedback prompt
            prompt = f"""Please update this system design based on QA feedback:

Current Design:
{design}

QA Feedback:
{qa_feedback}

Please provide updated design maintaining the same YAML format."""

            # Get updated design
            result = self.sa.agent.run(prompt)
            return result
            
        except Exception as e:
            PrettyOutput.print(f"Failed to update design: {str(e)}", OutputType.ERROR)
            return design

def main():
    """CLI entry point"""
    import argparse

    init_env()
    
    parser = argparse.ArgumentParser(description='Development team automation')
    parser.add_argument('requirement', help='Development requirement')
    args = parser.parse_args()
    
    team = DevTeam()
    result = team.handle_requirement(args.requirement)
    
    if result["success"]:
        PrettyOutput.print("Development completed successfully!", OutputType.SUCCESS)
        PrettyOutput.print(result["result"], OutputType.INFO)
    else:
        PrettyOutput.print(f"Development failed: {result['error']}", OutputType.ERROR)

if __name__ == "__main__":
    main()

from typing import List, Optional
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.multi_agent import MultiAgent, AgentConfig
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.utils import get_multiline_input

# Define system prompts for each role
PM_PROMPT = """You are a Project Manager (PM) responsible for:
1. Understanding client requirements and project goals
2. Creating and managing project plans
3. Coordinating with BA, SA, TL, DEV and QA
4. Ensuring project delivery and quality
5. Risk management and issue resolution
6. Status reporting and stakeholder communication

When receiving tasks:
1. Analyze requirements and create project plan
2. Delegate tasks to appropriate team members
3. Monitor progress and handle blockers
4. Ensure quality deliverables
5. Maintain project documentation

Communication Protocol:
- Send requirements to BA for analysis
- Coordinate with SA for technical architecture
- Work with TL for team coordination
- Monitor DEV progress through TL
- Ensure QA involvement for quality

Always maintain professional communication and focus on project success."""

BA_PROMPT = """You are a Business Analyst (BA) responsible for:
1. Analyzing business requirements
2. Creating detailed functional specifications
3. Working with stakeholders to clarify requirements
4. Documenting user stories and acceptance criteria
5. Supporting the development team with requirement clarifications

When receiving tasks:
1. Analyze business requirements thoroughly
2. Create clear, detailed specifications
3. Break down requirements into user stories
4. Define acceptance criteria
5. Coordinate with SA for technical feasibility

Communication Protocol:
- Receive requirements from PM
- Collaborate with SA for technical validation
- Share specifications with TL and DEV
- Support QA with test scenario creation"""

SA_PROMPT = """You are a Solution Architect (SA) responsible for:
1. Designing technical architecture
2. Ensuring technical feasibility
3. Making technology choices
4. Defining technical standards
5. Providing technical guidance

When receiving tasks:
1. Review requirements from BA
2. Design technical solutions
3. Create architecture documents
4. Define technical constraints
5. Guide implementation approach

Communication Protocol:
- Review BA's specifications
- Share architecture decisions with TL
- Guide DEV team through TL
- Ensure technical quality standards"""

TL_PROMPT = """You are a Technical Lead (TL) responsible for:
1. Technical team leadership
2. Code review management
3. Technical decision making
4. Development coordination
5. Technical problem solving

When receiving tasks:
1. Review technical requirements
2. Plan development approach
3. Assign tasks to developers
4. Monitor technical quality
5. Handle technical issues

Communication Protocol:
- Coordinate with SA for architecture
- Guide DEV team implementation
- Ensure QA requirements are met
- Report progress to PM"""

DEV_PROMPT = """You are a Developer (DEV) responsible for:
1. Implementing features
2. Writing clean, maintainable code
3. Following coding standards
4. Unit testing
5. Code documentation

When receiving tasks:
1. Review requirements and technical specs
2. Implement features
3. Write unit tests
4. Document code
5. Participate in code reviews

Communication Protocol:
- Take direction from TL
- Clarify requirements with BA
- Follow SA's architecture
- Support QA with bug fixes"""

QA_PROMPT = """You are a Quality Assurance (QA) engineer responsible for:
1. Test planning and execution
2. Bug reporting and tracking
3. Quality metrics monitoring
4. Test automation
5. Release validation

When receiving tasks:
1. Review requirements and acceptance criteria
2. Create test plans and cases
3. Execute test scenarios
4. Report defects
5. Validate fixes

Communication Protocol:
- Review BA's specifications
- Coordinate with TL for testing
- Report issues to DEV through TL
- Provide quality reports to PM"""

def create_dev_team() -> MultiAgent:
    """Create a development team with multiple agents."""
    
    # Create configurations for each role
    configs = [
        AgentConfig(
            name="PM",
            description="Project Manager - Coordinates team and manages project delivery",
            system_prompt=PM_PROMPT,
            # PM needs tools for project coordination and information gathering
            tool_registry=[
                "ask_user",          # Get clarification from stakeholders
                "ask_codebase",      # Review codebase status
                "search",            # Search for information
                "rag",               # Access project documentation
                "execute_shell",     # Execute system commands
                "read_code",         # Read code
            ],
            platform=PlatformRegistry().get_thinking_platform(),
        ),
        AgentConfig(
            name="BA",
            description="Business Analyst - Analyzes and documents requirements",
            system_prompt=BA_PROMPT,
            # BA needs tools for requirement analysis and documentation
            tool_registry=[
                "ask_user",          # Gather requirements
                "ask_codebase",      # Understand existing functionality
                "rag",               # Access and update documentation
                "search",            # Research similar solutions
                "execute_shell",     # Execute system commands
                "read_code",         # Read code
            ],
            platform=PlatformRegistry().get_thinking_platform(),
        ),
        AgentConfig(
            name="SA",
            description="Solution Architect - Designs technical solutions",
            system_prompt=SA_PROMPT,
            # SA needs tools for architecture design and technical analysis
            tool_registry=[
                "read_code",         # Analyze code structure
                "ask_codebase",      # Understand codebase
                "lsp_get_document_symbols",  # Analyze code structure
                "search",            # Research technical solutions
                "rag",               # Access technical documentation
                "execute_shell",     # Execute system commands
                "file_operation",    # File operation
            ],
            platform=PlatformRegistry().get_thinking_platform(),
        ),
        AgentConfig(
            name="TL",
            description="Technical Lead - Leads development team and ensures technical quality",
            system_prompt=TL_PROMPT,
            # TL needs tools for code review and technical coordination
            tool_registry=[
                "read_code",         # Review code
                "lsp_validate_edit", # Validate code changes
                "lsp_get_diagnostics", # Check code quality
                "ask_codebase",      # Understand codebase
                "lsp_find_references",  # Analyze code dependencies
                "lsp_find_definition",  # Navigate code
                "file_operation",    # File operation
            ],
            platform=PlatformRegistry().get_thinking_platform(),
        ),
        AgentConfig(
            name="DEV",
            description="Developer - Implements features and writes code",
            system_prompt=DEV_PROMPT,
            # DEV needs tools for code implementation
            tool_registry=[
                "ask_user",          # Get clarification from stakeholders
                "create_code_agent",    # Create a code agent
            ],
            platform=PlatformRegistry().get_normal_platform(),
        ),
        AgentConfig(
            name="QA",
            description="Quality Assurance - Ensures product quality through testing",
            system_prompt=QA_PROMPT,
            # QA needs tools for testing and quality assurance
            tool_registry=[
                "ask_user",          # Get clarification from stakeholders
                "create_code_agent", # Create a code agent
                "execute_shell",     # Run tests
                "ask_codebase",      # Understand test requirements
                "file_operation",    # File operation
            ],
            platform=PlatformRegistry().get_thinking_platform(),
        )
    ]
    
    return MultiAgent(configs, "PM")

def main():
    """Main entry point for the development team simulation."""
    
    # Create the development team
    dev_team = create_dev_team()
    
    # Start interaction loop
    while True:
        try:
            user_input = get_multiline_input("\nEnter your request (or press Enter to exit): ")
            if not user_input:
                break
                
            result = dev_team.run(user_input)
            print("\nFinal Result:", result)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {str(e)}")
            continue

if __name__ == "__main__":
    main()

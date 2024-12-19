from typing import Dict, Any

def validate_step_format(analysis: Dict[str, Any], logger) -> bool:
    """Validate single step analysis format"""
    try:
        # Check analysis section
        if not isinstance(analysis.get("analysis"), dict):
            logger.log('VALIDATION', "Analysis section is not a dictionary", is_error=True)
            return False
        
        analysis_dict = analysis["analysis"]
        required_fields = [
            "task_goal", "current_info", 
            "missing_info", "evidence"
        ]
        
        # 验证所有必需字段存在且格式正确
        for field in required_fields:
            if field not in analysis_dict:
                logger.log('VALIDATION', f"Missing required field: {field}", is_error=True)
                return False
            
        if not isinstance(analysis_dict["task_goal"], str):
            logger.log('VALIDATION', "task_goal must be a string", is_error=True)
            return False
        if not isinstance(analysis_dict["current_info"], str):
            logger.log('VALIDATION', "current_info must be a string", is_error=True)
            return False
        if not isinstance(analysis_dict["missing_info"], str):
            logger.log('VALIDATION', "missing_info must be a string", is_error=True)
            return False
        if not isinstance(analysis_dict["evidence"], list):
            logger.log('VALIDATION', "evidence must be a list", is_error=True)
            return False
        
        # Check next_step section
        next_step = analysis.get("next_step")
        if next_step is not None:  # Allow null for completed tasks
            if not isinstance(next_step, dict):
                logger.log('VALIDATION', "next_step must be a dictionary", is_error=True)
                return False
            required_fields = ["tool", "parameters", "description", "success_criteria"]
            missing_fields = [f for f in required_fields if f not in next_step]
            if missing_fields:
                logger.log('VALIDATION', f"Missing required fields in next_step: {missing_fields}", is_error=True)
                return False
            if not isinstance(next_step["parameters"], dict):
                logger.log('VALIDATION', "parameters must be a dictionary", is_error=True)
                return False
            if not isinstance(next_step["success_criteria"], list):
                logger.log('VALIDATION', "success_criteria must be a list", is_error=True)
                return False
            if not isinstance(next_step["description"], str):
                logger.log('VALIDATION', "description must be a string", is_error=True)
                return False
            if not next_step["description"].strip():
                logger.log('VALIDATION', "description cannot be empty", is_error=True)
                return False
        
        # Check required_tasks field
        if not isinstance(analysis.get("required_tasks"), list):
            logger.log('VALIDATION', "required_tasks must be a list", is_error=True)
            return False
        
        return True
        
    except Exception as e:
        logger.log('VALIDATION', f"Validation error: {str(e)}", is_error=True)
        return False 
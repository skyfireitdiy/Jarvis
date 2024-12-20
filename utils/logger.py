"""Logger module for pretty printing messages"""

class Logger:
    """Simple logger for pretty printing messages"""
    
    def info(self, message: str):
        """Print an info message"""
        print(message)
        
    def error(self, message: str):
        """Print an error message"""
        print("❌", message)
        
    def warning(self, message: str):
        """Print a warning message"""
        print("⚠️", message)
        
    def success(self, message: str):
        """Print a success message"""
        print("✅", message)
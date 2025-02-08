from jarvis.models.registry import PlatformRegistry
from jarvis.utils import PrettyOutput, OutputType, load_env_from_file, get_multiline_input

def list_platforms():
    """List all supported platforms and models"""
    registry = PlatformRegistry.get_global_platform_registry()
    platforms = registry.get_available_platforms()
    
    PrettyOutput.section("Supported platforms and models", OutputType.SUCCESS)
    
    for platform_name in platforms:
        # Create platform instance
        platform = registry.create_platform(platform_name)
        if not platform:
            continue
            
        # Get the list of models supported by the platform
        try:
            models = platform.get_model_list()
            
            # Print platform name
            PrettyOutput.section(f"{platform_name}", OutputType.SUCCESS)
            
            # Print model list
            if models:
                for model_name, description in models:
                    if description:
                        PrettyOutput.print(f"  • {model_name} - {description}", OutputType.SUCCESS)
                    else:
                        PrettyOutput.print(f"  • {model_name}", OutputType.SUCCESS)
            else:
                PrettyOutput.print("  • No available model information", OutputType.WARNING)
                
        except Exception as e:
            PrettyOutput.print(f"Failed to get model list for {platform_name}: {str(e)}", OutputType.WARNING)

def chat_with_model(platform_name: str, model_name: str):
    """Chat with specified platform and model"""
    registry = PlatformRegistry.get_global_platform_registry()
    
    # Create platform instance
    platform = registry.create_platform(platform_name)
    if not platform:
        PrettyOutput.print(f"Failed to create platform {platform_name}", OutputType.ERROR)
        return
    
    try:
        # Set model
        platform.set_model_name(model_name)
        PrettyOutput.print(f"Connected to {platform_name} platform {model_name} model", OutputType.SUCCESS)
        
        # Start conversation loop
        while True:
            # Get user input
            user_input = get_multiline_input("")
            
            # Check if input is cancelled
            if user_input == "__interrupt__" or user_input.strip() == "/bye":
                PrettyOutput.print("Bye!", OutputType.SUCCESS)
                break
                
            # Check if input is empty
            if not user_input.strip():
                continue
                
            # Check if it is a clear session command
            if user_input.strip() == "/clear":
                try:
                    platform.delete_chat()
                    platform.set_model_name(model_name)  # Reinitialize session
                    PrettyOutput.print("Session cleared", OutputType.SUCCESS)
                except Exception as e:
                    PrettyOutput.print(f"Failed to clear session: {str(e)}", OutputType.ERROR)
                continue
                
            try:
                # Send to model and get reply
                response = platform.chat_until_success(user_input)
                if not response:
                    PrettyOutput.print("No valid reply", OutputType.WARNING)
                    
            except Exception as e:
                PrettyOutput.print(f"Failed to chat: {str(e)}", OutputType.ERROR)
                
    except Exception as e:
        PrettyOutput.print(f"Failed to initialize conversation: {str(e)}", OutputType.ERROR)
    finally:
        # Clean up resources
        try:
            platform.delete_chat()
        except:
            pass

def info_command(args):
    """Process info subcommand"""
    list_platforms()

def chat_command(args):
    """Process chat subcommand"""
    if not args.platform or not args.model:
        PrettyOutput.print("Please specify platform and model. Use 'jarvis info' to view available platforms and models.", OutputType.ERROR)
        return
    chat_with_model(args.platform, args.model)

def main():
    """Main function"""
    import argparse

    load_env_from_file()
    
    parser = argparse.ArgumentParser(description='Jarvis AI Platform')
    subparsers = parser.add_subparsers(dest='command', help='Available subcommands')
    
    # info subcommand
    info_parser = subparsers.add_parser('info', help='Display supported platforms and models information')
    
    # chat subcommand
    chat_parser = subparsers.add_parser('chat', help='Chat with specified platform and model')
    chat_parser.add_argument('--platform', '-p', help='Specify the platform to use')
    chat_parser.add_argument('--model', '-m', help='Specify the model to use')
    
    args = parser.parse_args()
    
    if args.command == 'info':
        info_command(args)
    elif args.command == 'chat':
        chat_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
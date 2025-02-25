from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils import PrettyOutput, OutputType, init_env, get_multiline_input

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
            
            output = ""
            # Print model list
            if models:
                for model_name, description in models:
                    if description:
                        output += f"  • {model_name} - {description}\n"
                    else:
                        output += f"  • {model_name}\n"
                PrettyOutput.print(output, OutputType.SUCCESS, lang="markdown")
            else:
                PrettyOutput.print("  • 没有可用的模型信息", OutputType.WARNING)
                
        except Exception as e:
            PrettyOutput.print(f"获取 {platform_name} 的模型列表失败: {str(e)}", OutputType.WARNING)

def chat_with_model(platform_name: str, model_name: str):
    """Chat with specified platform and model"""
    registry = PlatformRegistry.get_global_platform_registry()
    
    # Create platform instance
    platform = registry.create_platform(platform_name)
    if not platform:
        PrettyOutput.print(f"创建平台 {platform_name} 失败", OutputType.ERROR)
        return
    
    try:
        # Set model
        platform.set_model_name(model_name)
        PrettyOutput.print(f"连接到 {platform_name} 平台 {model_name} 模型", OutputType.SUCCESS)
        
        # Start conversation loop
        while True:
            # Get user input
            user_input = get_multiline_input("")
            
            # Check if input is cancelled
            if user_input.strip() == "/bye":
                PrettyOutput.print("再见!", OutputType.SUCCESS)
                break
                
            # Check if input is empty
            if not user_input.strip():
                continue
                
            # Check if it is a clear session command
            if user_input.strip() == "/clear":
                try:
                    platform.delete_chat()
                    platform.set_model_name(model_name)  # Reinitialize session
                    PrettyOutput.print("会话已清除", OutputType.SUCCESS)
                except Exception as e:
                    PrettyOutput.print(f"清除会话失败: {str(e)}", OutputType.ERROR)
                continue
                
            try:
                # Send to model and get reply
                response = platform.chat_until_success(user_input)
                if not response:
                    PrettyOutput.print("没有有效的回复", OutputType.WARNING)
                    
            except Exception as e:
                PrettyOutput.print(f"聊天失败: {str(e)}", OutputType.ERROR)
                
    except Exception as e:
        PrettyOutput.print(f"初始化会话失败: {str(e)}", OutputType.ERROR)
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
        PrettyOutput.print("请指定平台和模型。使用 'jarvis info' 查看可用平台和模型。", OutputType.ERROR)
        return
    chat_with_model(args.platform, args.model)

def main():
    """Main function"""
    import argparse

    init_env()
    
    parser = argparse.ArgumentParser(description='Jarvis AI 平台')
    subparsers = parser.add_subparsers(dest='command', help='可用子命令')
    
    # info subcommand
    info_parser = subparsers.add_parser('info', help='显示支持的平台和模型信息')
    
    # chat subcommand
    chat_parser = subparsers.add_parser('chat', help='与指定平台和模型聊天')
    chat_parser.add_argument('--platform', '-p', help='指定要使用的平台')
    chat_parser.add_argument('--model', '-m', help='指定要使用的模型')
    
    args = parser.parse_args()
    
    if args.command == 'info':
        info_command(args)
    elif args.command == 'chat':
        chat_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
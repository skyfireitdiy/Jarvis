#!/usr/bin/env python3
"""
Test script for Jarvis OpenAI-compatible API service.
"""

import argparse
import sys
from openai import OpenAI

def test_chat(api_base, model, stream=False, interactive=False):
    """Test chat completion with the API."""
    client = OpenAI(
        api_key="dummy-key",  # Not actually used by our service
        base_url=f"{api_base}/v1"
    )

    print(f"Testing chat with model: {model}, stream={stream}")
    print("=" * 50)

    try:
        # First, list available models
        print("Available models:")
        models = client.models.list()
        for m in models.data:
            print(f"  - {m.id}")
        print()

        if interactive:
            # Interactive chat mode
            messages = [
                {"role": "system", "content": "You are a helpful assistant."}
            ]

            print("Interactive chat mode. Type 'exit' to quit.")
            print("=" * 50)

            while True:
                # Get user input
                user_input = input("You: ")
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    break

                # Add user message to history
                messages.append({"role": "user", "content": user_input})

                # Get response
                print("Assistant: ", end="", flush=True)

                if stream:
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages, # type: ignore
                        stream=True
                    ) # type: ignore

                    # Process the streaming response
                    assistant_response = ""
                    for chunk in response:
                        if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            assistant_response += content
                            print(content, end="", flush=True)
                    print()
                else:
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages # type: ignore
                    )
                    assistant_response = response.choices[0].message.content
                    print(assistant_response)

                # Add assistant response to history
                messages.append({"role": "assistant", "content": assistant_response}) # type: ignore
                print()

            print("=" * 50)
            print("Chat session ended.")

        else:
            # Single request mode
            print("Sending chat request...")
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello! Tell me a short joke."}
            ]

            if stream:
                print("Response (streaming):")

                # Use the OpenAI client for streaming
                response = client.chat.completions.create(
                    model=model,
                    messages=messages, # type: ignore
                    stream=True
                ) # type: ignore

                # Process the streaming response
                full_content = ""
                for chunk in response:
                    if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_content += content
                        print(content, end="", flush=True)

                print("\n")
                print(f"Full response: {full_content}")
            else:
                print("Response:")
                response = client.chat.completions.create(
                    model=model,
                    messages=messages # type: ignore
                )
                print(response.choices[0].message.content)

        print("=" * 50)
        print("Test completed successfully!")

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

def main():
    parser = argparse.ArgumentParser(description="Test Jarvis OpenAI-compatible API")
    parser.add_argument("--api-base", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--model", default="gpt-3.5-turbo", help="Model to test (default: gpt-3.5-turbo)")
    parser.add_argument("--stream", action="store_true", help="Test streaming mode")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive chat mode")

    args = parser.parse_args()

    return test_chat(args.api_base, args.model, args.stream, args.interactive)

if __name__ == "__main__":
    sys.exit(main())

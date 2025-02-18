from flask import Flask, request, jsonify
from datetime import datetime
import time
import uuid

app = Flask(__name__)

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def chat_completions():
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
        
    try:
        data = request.get_json()
        
        # 验证请求数据
        if not data or 'messages' not in data:
            return jsonify({
                "error": {
                    "message": "messages is required",
                    "type": "invalid_request_error",
                    "code": "invalid_request"
                }
            }), 400

        for message in data['messages']:
            print(message['role'] ," : ",message['content'])

        response = []
        while True:
            i = input(">>>")
            if i == "EOF":
                break
            response.append(i)
        
        # 构造响应
        response = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get('model', 'gpt-3.5-turbo'),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "\n".join(response)
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
        
        return jsonify(response)

    except Exception as e:
        return jsonify({
            "error": {
                "message": str(e),
                "type": "server_error",
                "code": "internal_server_error"
            }
        }), 500

@app.route('/v1/models', methods=['GET', 'OPTIONS'])
def list_models():
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    models = {
        "data": [
            {
                "id": "test_model",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "fakeopenai"
            }
        ],
        "object": "list"
    }
    return jsonify(models)

# 添加全局CORS支持
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)

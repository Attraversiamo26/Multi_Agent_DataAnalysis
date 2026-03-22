import yaml
import requests
import json

# 读取配置文件
with open('conf.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 获取大模型配置
llm_config = config['llm']['plan_agent']
api_key = llm_config['api_key']
base_url = llm_config['base_url']
# model: qwen3-vl-plus-2025-12-19
model = llm_config['model']

print(f"测试大模型连接：")
print(f"模型：{model}")
print(f"Base URL：{base_url}")
print(f"API Key：{api_key[:4]}...{api_key[-4:]}")

# 测试连接
try:
    # 构建请求
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "你好"
            }
        ],
        "temperature": 0.7,
        "max_tokens": 50
    }
    
    print("\n发送请求...")
    # 发送请求
    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=data,
        timeout=10
    )
    
    print(f"响应状态码：{response.status_code}")
    # 处理响应
    if response.status_code == 200:
        result = response.json()
        print("✅ 大模型连接成功！")
        print(f"响应：{result['choices'][0]['message']['content']}")
    else:
        print(f"❌ 大模型连接失败：{response.status_code}")
        print(f"响应：{response.text[:500]}...")
        
except requests.exceptions.Timeout:
    print("❌ 连接超时：可能是网络问题或API服务不可用")
except requests.exceptions.ConnectionError:
    print("❌ 连接错误：无法连接到API服务器")
except Exception as e:
    print(f"❌ 测试失败：{str(e)}")

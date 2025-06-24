#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试图片角色API调用
"""

import os
import requests
import json

# API配置
API_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
API_KEY_PATH = os.path.join(os.path.dirname(__file__), "API-KEY.txt")

def load_api_key():
    """加载API密钥"""
    try:
        with open(API_KEY_PATH, 'r') as f:
            return f.read().strip()
    except Exception as e:
        print(f"错误：无法加载API密钥: {e}")
        return None

def test_quick_api_call():
    """快速测试API调用"""
    api_key = load_api_key()
    if not api_key:
        print("无法加载API密钥")
        return
    
    # 使用已上传的图片URL
    image_url = "https://i.ibb.co/bjMVNnft/seedance-a228507a-2ba0-4348-90fb-68169f9701ad.jpg"
    
    # 测试start和end角色
    payload = {
        "model": "doubao-seedance-1-0-lite-i2v-250428",
        "content": [
            {
                "type": "text",
                "text": "天空的云飘动着，路上的车辆行驶 --resolution 720p --duration 5 --camerafixed false"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url
                },
                "role": "start"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url
                },
                "role": "end"
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    print("=== 测试start/end角色 ===")
    print(f"发送请求到: {API_URL}")
    print(f"图片URL: {image_url}")
    
    try:
        print("发送API请求...")
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            task_id = result.get("id")
            print(f"✅ 任务创建成功！")
            print(f"任务ID: {task_id}")
        else:
            print(f"❌ 请求失败")
            try:
                error_data = response.json()
                print(f"错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"响应内容: {response.text}")
                
    except requests.Timeout:
        print("❌ 请求超时")
    except Exception as e:
        print(f"❌ 请求异常: {e}")

if __name__ == "__main__":
    print("快速角色测试")
    print("=" * 30)
    test_quick_api_call()
    print("测试完成！")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试Seedance任务状态
"""

import os
import sys
import requests
import json
import time

# 添加当前目录到path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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

def create_and_monitor_task():
    """创建任务并监控完整状态变化"""
    api_key = load_api_key()
    if not api_key:
        print("无法加载API密钥")
        return
    
    # 使用官方示例图片
    test_image_url = "https://ark-project.tos-cn-beijing.volces.com/doc_image/see_i2v.jpeg"
    
    # 创建lite模型任务（含收尾帧）
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
                    "url": test_image_url
                }
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": test_image_url  # 同一张图作为收尾帧
                }
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    print("=== 创建任务 ===")
    print(f"模型: {payload['model']}")
    print(f"内容项: {len(payload['content'])}")
    
    try:
        # 1. 创建任务
        print("发送创建任务请求...")
        response = requests.post(API_URL, headers=headers, json=payload)
        
        print(f"创建任务响应状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"创建任务失败: {response.text}")
            return
        
        result = response.json()
        task_id = result.get("id")
        
        if not task_id:
            print(f"未获取到任务ID: {result}")
            return
        
        print(f"✅ 任务创建成功")
        print(f"任务ID: {task_id}")
        print(f"初始响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        # 2. 监控任务状态
        print(f"\n=== 开始监控任务状态 ===")
        status_url = f"{API_URL}/{task_id}"
        
        previous_status = None
        attempt = 0
        max_attempts = 120  # 10分钟
        
        while attempt < max_attempts:
            try:
                time.sleep(3)  # 每3秒检查一次
                attempt += 1
                
                status_response = requests.get(status_url, headers=headers)
                
                if status_response.status_code != 200:
                    print(f"获取状态失败: {status_response.status_code} - {status_response.text}")
                    continue
                
                status_data = status_response.json()
                current_status = status_data.get("status")
                progress = status_data.get("progress", 0)
                
                # 只在状态变化时打印详细信息
                if current_status != previous_status:
                    print(f"\n[尝试 {attempt}] 状态变化: {previous_status} -> {current_status}")
                    print(f"进度: {progress}%")
                    print(f"完整状态数据: {json.dumps(status_data, indent=2, ensure_ascii=False)}")
                    previous_status = current_status
                else:
                    # 相同状态只打印简要信息
                    print(f"[尝试 {attempt}] 状态: {current_status}, 进度: {progress}%")
                
                # 检查终止状态
                if current_status == "succeeded":
                    print(f"\n🎉 任务成功完成！")
                    content = status_data.get("content", {})
                    video_url = content.get("video_url")
                    if video_url:
                        print(f"视频URL: {video_url}")
                    else:
                        print("⚠️ 未找到视频URL")
                        print(f"Content数据: {json.dumps(content, indent=2, ensure_ascii=False)}")
                    break
                    
                elif current_status == "failed":
                    print(f"\n❌ 任务失败")
                    error = status_data.get("error", {})
                    failure_reason = status_data.get("failure_reason", "未提供失败原因")
                    print(f"错误信息: {json.dumps(error, indent=2, ensure_ascii=False)}")
                    print(f"失败原因: {failure_reason}")
                    break
                    
                elif current_status in ["queued", "running", "processing", "pending"]:
                    # 继续监控
                    continue
                else:
                    print(f"⚠️ 未知状态: {current_status}")
                    
            except Exception as e:
                print(f"监控状态时出错: {e}")
                time.sleep(5)
        
        if attempt >= max_attempts:
            print(f"\n⏰ 监控超时（{max_attempts} 次尝试）")
            print(f"最后状态: {previous_status}")
            
    except Exception as e:
        print(f"❌ 异常: {e}")

if __name__ == "__main__":
    print("Seedance 任务状态调试工具")
    print("=" * 50)
    create_and_monitor_task()
    print("\n调试完成！")

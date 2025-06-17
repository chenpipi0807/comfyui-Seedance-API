import os
import sys
import time
import json
import requests
import uuid
import torch
from PIL import Image
import numpy as np
from pathlib import Path

# Import our image server module
from .image_server import get_image_url

# Get the directory of the current file
NODE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
# ComfyUI output directory
OUTPUT_DIR = Path(os.path.abspath(os.path.join(NODE_DIR.parent.parent, "output")))
# Create seedance output directory if it doesn't exist
SEEDANCE_OUTPUT_DIR = OUTPUT_DIR / "seedance"
os.makedirs(SEEDANCE_OUTPUT_DIR, exist_ok=True)

# Define global constants
API_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
API_KEY_PATH = os.path.join(NODE_DIR, "API-KEY.txt")
# Available models
SEEDANCE_MODELS = [
    "doubao-seedance-1-0-pro-250528",
    "doubao-seedance-1-0-lite-i2v-250428"
]

def load_api_key():
    """Load API key from file"""
    try:
        with open(API_KEY_PATH, 'r') as f:
            return f.read().strip()
    except Exception as e:
        print(f"Error loading API key: {e}")
        return None

def tensor_to_img(tensor):
    """Convert a tensor to a PIL Image"""
    # Check if tensor is batched
    if len(tensor.shape) == 4:  # BCHW format
        tensor = tensor[0]  # Take first image if batched
    
    # Convert from CHW to HWC
    if tensor.shape[0] in [1, 3]:  # If channels first (CHW)
        tensor = tensor.permute(1, 2, 0)
    
    # Ensure values are in [0, 1]
    if tensor.max() > 1.0:
        tensor = tensor / 255.0
        
    # Convert to numpy array
    img_np = tensor.cpu().numpy()
    
    # Handle different channel configurations
    if img_np.shape[2] == 1:  # Grayscale
        img_np = np.repeat(img_np, 3, axis=2)
    elif img_np.shape[2] == 4:  # RGBA
        img_np = img_np[:, :, :3]  # Just take RGB channels
    
    # Convert to uint8 for PIL
    img_np = (img_np * 255).astype(np.uint8)
    
    # Convert to PIL Image
    return Image.fromarray(img_np)

def save_image_for_api(tensor, filename=None):
    """Save tensor as image and return file path"""
    if filename is None:
        filename = f"seedance_input_{uuid.uuid4()}.png"
    
    filepath = os.path.join(SEEDANCE_OUTPUT_DIR, filename)
    img = tensor_to_img(tensor)
    img.save(filepath)
    return filepath

class SeedanceGenerator:
    """
    ComfyUI node to generate videos using Doubao Seedance API from input images
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (SEEDANCE_MODELS, {"default": "doubao-seedance-1-0-pro-250528"}),
                "image": ("IMAGE", {"description": "首帧图片"}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (["480p", "720p", "1080p"], {"default": "1080p"}),
                "duration": (["5s", "10s"], {"default": "5s"}),
                "camera_fixed": ("BOOLEAN", {"default": False}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
            },
            "optional": {
                "end_frame_image": ("IMAGE", {"description": "尾帧图片（可选）"}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("视频路径",)
    FUNCTION = "generate_video"
    CATEGORY = "豆包 API"
    
    def generate_video(self, model, image, prompt, resolution, duration, camera_fixed, seed, end_frame_image=None):
        # 1. Save first frame image to file
        input_image_path = save_image_for_api(image, f"seedance_first_frame_{uuid.uuid4()}.png")
        
        # 2. Upload images for API access
        # Get a publicly accessible URL for the first frame using our image server
        first_frame_url = get_image_url(input_image_path)
        print(f"First frame URL: {first_frame_url}")
        
        # 3. Prepare API request parameters
        api_key = load_api_key()
        if not api_key:
            print("Failed to load API key")
            return ("ERROR: Failed to load API key",)
        
        # 从duration字符串中提取秒数
        duration_seconds = duration.replace("s", "")
        
        # Format the prompt with parameters
        seed_param = f"--seed {seed}" if seed >= 0 else ""
        formatted_prompt = f"{prompt} --resolution {resolution} --duration {duration_seconds} --camerafixed {str(camera_fixed).lower()} {seed_param}".strip()
        
        # Prepare content list with prompt and first frame
        content_list = [
            {
                "type": "text",
                "text": formatted_prompt
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": first_frame_url
                }
            }
        ]
        
        # Add end frame if provided
        if end_frame_image is not None:
            end_frame_path = save_image_for_api(end_frame_image, f"seedance_end_frame_{uuid.uuid4()}.png")
            end_frame_url = get_image_url(end_frame_path)
            print(f"End frame URL: {end_frame_url}")
            
            content_list.append({
                "type": "image_url",
                "image_url": {
                    "url": end_frame_url
                }
            })
        
        # Prepare request data
        payload = {
            "model": model,
            "content": content_list
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # 4. Make API request
        try:
            print(f"Sending request to Seedance API: {formatted_prompt}")
            response = requests.post(API_URL, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            task_id = result.get("id")
            
            if not task_id:
                print(f"Error: No task ID received. Response: {response.text}")
                return ("ERROR: Failed to create task",)
                
            print(f"Task created with ID: {task_id}")
            
            # 5. Poll for results
            video_url = self._poll_task_status(task_id, api_key)
            if not video_url:
                return ("ERROR: Task failed or timed out",)
            
            # 6. Download video
            output_path = os.path.join(SEEDANCE_OUTPUT_DIR, f"seedance_output_{task_id}.mp4")
            self._download_video(video_url, output_path)
            
            print(f"Video downloaded to: {output_path}")
            return (output_path,)
            
        except requests.RequestException as e:
            print(f"Request error: {e}")
            return (f"ERROR: {str(e)}",)
        except Exception as e:
            print(f"Unexpected error: {e}")
            return (f"ERROR: {str(e)}",)
    
    def _poll_task_status(self, task_id, api_key, max_attempts=60, delay=5):
        """Poll the API for task status"""
        status_url = f"{API_URL}/{task_id}"
        headers = {"Authorization": f"Bearer {api_key}"}
        print(f"开始轮询任务 {task_id} 状态，最多轮询 {max_attempts} 次，每 {delay} 秒一次")
        
        for attempt in range(max_attempts):
            try:
                response = requests.get(status_url, headers=headers)
                response.raise_for_status()
                result = response.json()
                
                status = result.get("status")
                
                # 只在状态变更时打印日志
                if attempt == 0 or status != "processing" and status != "running" and status != "pending":
                    print(f"当前状态: {status}")
                
                if status == "succeeded":
                    # 从API响应中提取视频URL
                    # 豆包API的视频URL在content.video_url中，而不是outputs数组
                    content = result.get("content", {})
                    video_url = content.get("video_url")
                    
                    if video_url:
                        print(f"找到视频URL: {video_url}")
                        return video_url
                    else:
                        print("错误: 没有在结果中找到视频URL")
                        print(f"完整的响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")
                        return None
                    
                elif status == "failed":
                    error = result.get("error", {})
                    print(f"任务失败: {json.dumps(error, ensure_ascii=False)}")
                    reason = result.get("failure_reason", "未提供失败原因")
                    print(f"失败原因: {reason}")
                    return None
                elif status == "processing" or status == "pending" or status == "running":
                    progress = result.get("progress", 0)
                    print(f"处理中... 状态: {status}, 进度: {progress}%")
                else:
                    print(f"未知状态: {status}")
                
                # 如果仍在处理，等待并重试
                time.sleep(delay)
                
            except requests.exceptions.HTTPError as e:
                print(f"HTTP错误: {e}")
                print(f"响应状态码: {e.response.status_code}")
                print(f"响应内容: {e.response.text}")
                time.sleep(delay)
            except Exception as e:
                print(f"轮询任务状态时出错: {e}")
                time.sleep(delay)
        
        print("任务轮询超时，请检查API密钥是否有效，或稍后重试")
        return None
    
    def _download_video(self, url, output_path):
        """Download video from URL"""
        try:
            print(f"正在下载视频: {url[:100]}...")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print(f"视频成功下载到: {output_path}")
            return True
        except Exception as e:
            print(f"下载视频时出错: {e}")
            return False



# Node registration
NODE_CLASS_MAPPINGS = {
    "SeedanceGenerator": SeedanceGenerator
}

# Display names for nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "SeedanceGenerator": "豆包 图生视频生成"
}

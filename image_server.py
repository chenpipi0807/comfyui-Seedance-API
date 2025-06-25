import os
import requests
import base64
import json
import uuid
from pathlib import Path

# 常量
IMGBB_API_URL = "https://api.imgbb.com/1/upload"

# 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMGBB_KEY_PATH = os.path.join(SCRIPT_DIR, "IMGBB-KEY.txt")

def get_api_key_path():
    """Get path for imgbb API key"""
    node_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    return str(node_dir / "IMGBB-KEY.txt")

def load_imgbb_key():
    """Load ImgBB API key from file"""
    try:
        api_key_path = get_api_key_path()
        # Create empty key file if it doesn't exist
        if not os.path.exists(api_key_path):
            with open(api_key_path, 'w') as f:
                f.write("# Get your ImgBB API key from https://api.imgbb.com/ and paste it here")
            return None
            
        with open(api_key_path, 'r') as f:
            key = f.read().strip()
            # If key is empty or contains just a comment, return None
            if not key or key.startswith("#"):
                return None
            return key
    except Exception as e:
        print(f"Error loading ImgBB API key: {e}")
        return None

def load_imgbb_api_key():
    """从文件加载ImgBB API密钥"""
    try:
        if not os.path.exists(IMGBB_KEY_PATH):
            # 如果文件不存在，创建一个空文件供用户添加密钥
            with open(IMGBB_KEY_PATH, "w") as f:
                f.write("")
            return None
            
        with open(IMGBB_KEY_PATH, "r") as f:
            api_key = f.read().strip()
            return api_key if api_key else None
    except Exception as e:
        print(f"加载ImgBB API密钥出错: {e}")
        return None

def upload_image_to_imgbb(image_path):
    """将图片上传至ImgBB并返回URL"""
    api_key = load_imgbb_api_key()
    if not api_key:
        print("警告：未找到ImgBB API密钥或密钥无效。请在IMGBB-KEY.txt文件中设置密钥")
        return None
        
    try:
        with open(image_path, "rb") as file:
            image_data = base64.b64encode(file.read()).decode("utf-8")
            
        payload = {
            "key": api_key,
            "image": image_data,
            "name": f"seedance_{uuid.uuid4()}"
        }
        
        response = requests.post(IMGBB_API_URL, data=payload)
        response.raise_for_status()
        
        result = response.json()
        if result.get("success"):
            url = result.get("data", {}).get("url")
            print(f"图片已上传至ImgBB: {url}")
            return url
        else:
            print(f"上传图片出错: {result.get('error', {}).get('message')}")
            return None
            
    except Exception as e:
        print(f"上传图片至ImgBB出错: {e}")
        return None

def get_image_url(image_path):
    """获取图片的公开访问URL"""
    # 尝试上传到ImgBB
    url = upload_image_to_imgbb(image_path)
    if url:
        return url
        
    # 如果上传失败，警告用户
    print("""
    ====== 警告: 图片上传失败 ======
    豆包 Seedance API 需要公开可访问的图片URL。
    请确保:
    1. 在IMGBB-KEY.txt文件中设置了有效的ImgBB API密钥
    2. 检查网络连接
    3. ImgBB服务是否正常运行
    ============================
    """)
    
    # 返回本地路径作为后备，但这对API不起作用
    return f"file://{image_path}"

def upload_audio_to_imgbb(audio_path):
    """将音频文件上传至ImgBB并返回URL（ImgBB也支持音频文件）"""
    api_key = load_imgbb_api_key()
    if not api_key:
        print("警告：未找到ImgBB API密钥或密钥无效。请在IMGBB-KEY.txt文件中设置密钥")
        return None
        
    try:
        with open(audio_path, "rb") as file:
            audio_data = base64.b64encode(file.read()).decode("utf-8")
            
        payload = {
            "key": api_key,
            "image": audio_data,  # ImgBB uses 'image' parameter for all file types
            "name": f"omnihuman_audio_{uuid.uuid4()}"
        }
        
        response = requests.post(IMGBB_API_URL, data=payload)
        response.raise_for_status()
        
        result = response.json()
        if result.get("success"):
            url = result.get("data", {}).get("url")
            print(f"音频文件已上传至ImgBB: {url}")
            return url
        else:
            print(f"上传音频文件出错: {result.get('error', {}).get('message')}")
            return None
            
    except Exception as e:
        print(f"上传音频文件至ImgBB出错: {e}")
        return None

def get_audio_url(audio_path):
    """获取音频文件的公开访问URL"""
    if not audio_path or not os.path.exists(audio_path):
        return None
        
    # 尝试上传到ImgBB
    url = upload_audio_to_imgbb(audio_path)
    if url:
        return url
        
    # 如果上传失败，警告用户
    print("""
    ====== 警告: 音频文件上传失败 ======
    OmniHuman API 需要公开可访问的音频URL。
    请确保:
    1. 在IMGBB-KEY.txt文件中设置了有效的ImgBB API密钥
    2. 检查网络连接
    3. ImgBB服务是否正常运行
    ================================
    """)
    
    return None

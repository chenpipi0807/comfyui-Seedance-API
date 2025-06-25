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
import torchaudio
import base64
import hashlib
import hmac
from urllib.parse import quote, urlparse, parse_qs
import datetime

# Import our image server module
from .image_server import get_image_url, get_audio_url

# Get the directory of the current file
NODE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
# ComfyUI output directory
OUTPUT_DIR = Path(os.path.abspath(os.path.join(NODE_DIR.parent.parent, "output")))
# Create omnihuman output directory if it doesn't exist
OMNIHUMAN_OUTPUT_DIR = OUTPUT_DIR / "omnihuman"
os.makedirs(OMNIHUMAN_OUTPUT_DIR, exist_ok=True)

# API endpoints for OmniHuman - Official endpoints with query parameters
OMNIHUMAN_SUBMIT_URL = "https://visual.volcengineapi.com?Action=CVSubmitTask&Version=2022-08-31"
OMNIHUMAN_RESULT_URL = "https://visual.volcengineapi.com?Action=CVGetResult&Version=2022-08-31"
OMNIHUMAN_AK_SK_PATH = os.path.join(NODE_DIR, "OmniHuman_KEY.txt")

# Available OmniHuman models and configurations
OMNIHUMAN_MODELS = [
    "omnihuman-v1.0-standard",
    "omnihuman-v1.0-pro",
    "omnihuman-v1.0-lite"
]

OMNIHUMAN_RESOLUTIONS = ["720p", "1080p", "1440p"]
OMNIHUMAN_DURATIONS = ["3s", "5s", "10s", "15s"]

def load_ak_sk():
    """Load AK/SK from file"""
    try:
        with open(OMNIHUMAN_AK_SK_PATH, 'r') as f:
            lines = f.readlines()
            
        ak = None
        sk = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("AccessKeyId:"):
                ak = line.split(":", 1)[1].strip()
            elif line.startswith("SecretAccessKey:"):
                sk_encoded = line.split(":", 1)[1].strip()
                # Decode base64 SecretAccessKey
                try:
                    sk = base64.b64decode(sk_encoded).decode('utf-8')
                    print(f"成功解码SecretAccessKey")
                except:
                    sk = sk_encoded  # Use as-is if decode fails
                    print(f"SecretAccessKey未编码，直接使用")
        
        if ak and sk:
            print(f"成功加载AK/SK - AccessKeyId: {ak[:8]}..., SecretAccessKey: {sk[:8]}...")
            return ak, sk
        else:
            print("错误：AK或SK未找到")
            return None, None
            
    except Exception as e:
        print(f"Error loading AK/SK: {e}")
        return None, None

def sign_request(ak, sk, method, url, headers, body):
    """Generate signature for request using Volcano Engine standard algorithm"""
    from urllib.parse import urlparse, parse_qs
    
    # Parse URL
    parsed_url = urlparse(url)
    host = parsed_url.netloc
    path = parsed_url.path if parsed_url.path else '/'
    query = parsed_url.query
    
    # Generate timestamp
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    date_only = timestamp[:8]  # YYYYMMDD
    
    # Add required headers
    headers["Host"] = host
    headers["X-Date"] = timestamp
    headers["Content-Type"] = "application/json"
    
    # Step 1: Create Canonical Request
    # HTTPRequestMethod
    http_method = method.upper()
    
    # CanonicalURI
    canonical_uri = path
    
    # CanonicalQueryString - sort query parameters
    if query:
        query_params = parse_qs(query, keep_blank_values=True)
        sorted_params = []
        for key in sorted(query_params.keys()):
            for value in sorted(query_params[key]):
                sorted_params.append(f"{quote(key, safe='')}={quote(value, safe='')}")
        canonical_query = "&".join(sorted_params)
    else:
        canonical_query = ""
    
    # CanonicalHeaders - lowercase keys, sort by key, format as key:value
    canonical_headers_list = []
    signed_headers_list = []
    
    for key in sorted(headers.keys(), key=str.lower):
        key_lower = key.lower()
        canonical_headers_list.append(f"{key_lower}:{headers[key]}")
        signed_headers_list.append(key_lower)
    
    canonical_headers = "\n".join(canonical_headers_list) + "\n"
    signed_headers = ";".join(signed_headers_list)
    
    # RequestPayload hash
    payload_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()
    
    # Build canonical request
    canonical_request = f"{http_method}\n{canonical_uri}\n{canonical_query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    
    print(f"Canonical Request:\n{canonical_request}")
    
    # Step 2: Create String to Sign
    algorithm = "HMAC-SHA256"
    request_date = timestamp
    credential_scope = f"{date_only}/cn-north-1/cv/request"  # Using correct region and service per docs
    canonical_request_hash = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    
    string_to_sign = f"{algorithm}\n{request_date}\n{credential_scope}\n{canonical_request_hash}"
    
    print(f"String to Sign:\n{string_to_sign}")
    
    # Step 3: Build Signing Key using nested HMAC operations
    def hmac_sha256(key, data):
        return hmac.new(key, data.encode('utf-8'), hashlib.sha256).digest()
    
    # Signing key derivation: HMAC(HMAC(HMAC(HMAC(kSecret, date), region), service), "request")
    k_secret = sk.encode('utf-8')
    k_date = hmac_sha256(k_secret, date_only)
    k_region = hmac_sha256(k_date, "cn-north-1")
    k_service = hmac_sha256(k_region, "cv")
    signing_key = hmac_sha256(k_service, "request")
    
    # Step 4: Generate Signature
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    print(f"Generated Signature: {signature}")
    
    # Step 5: Add Authorization header
    authorization = f"HMAC-SHA256 Credential={ak}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
    headers["Authorization"] = authorization
    
    # Remove the old headers we don't need
    if "X-Volc-AK" in headers:
        del headers["X-Volc-AK"]
    if "X-Volc-Signature" in headers:
        del headers["X-Volc-Signature"]
    
    return headers

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
        filename = f"omnihuman_input_{uuid.uuid4()}.png"
    
    filepath = os.path.join(OMNIHUMAN_OUTPUT_DIR, filename)
    img = tensor_to_img(tensor)
    img.save(filepath)
    return filepath

def save_audio_for_api(tensor, filename=None):
    """Save tensor as audio and return file path"""
    if filename is None:
        filename = f"omnihuman_audio_{uuid.uuid4()}.wav"
    
    filepath = os.path.join(OMNIHUMAN_OUTPUT_DIR, filename)
    torchaudio.save(filepath, tensor)
    return filepath


class OmniHumanSubjectIdentifier:
    """
    ComfyUI node to identify and extract human subject from input image using OmniHuman API
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (OMNIHUMAN_MODELS, {"default": "omnihuman-v1.0-standard"}),
                "subject_image": ("IMAGE", {"description": "主体人物图片"}),
                "quality_check": ("BOOLEAN", {"default": True, "description": "启用质量检查"}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("主体ID", "状态信息")
    FUNCTION = "identify_subject"
    CATEGORY = "火山引擎 OmniHuman"
    
    def identify_subject(self, model, subject_image, quality_check):
        """识别主体并返回主体ID"""
        try:
            # Save and upload subject image
            subject_image_path = save_image_for_api(subject_image, f"omnihuman_subject_{uuid.uuid4()}.png")
            subject_image_url = get_image_url(subject_image_path)
            
            ak, sk = load_ak_sk()
            if not ak or not sk:
                return ("", "错误: 无法加载AK/SK")
            
            # Prepare subject identification request
            headers = {
                "Content-Type": "application/json"
            }
            
            # Official API request body structure
            payload = {
                "req_key": "realman_avatar_picture_create_role_omni",
                "image_url": subject_image_url
            }
            
            signed_headers = sign_request(ak, sk, "POST", OMNIHUMAN_SUBMIT_URL, headers, json.dumps(payload))
            
            print(f"发送主体识别请求到: {OMNIHUMAN_SUBMIT_URL}")
            print(f"请求头: {signed_headers}")
            print(f"请求体: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            response = requests.post(OMNIHUMAN_SUBMIT_URL, headers=signed_headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Check if it's an async task
            if "task_id" in result:
                task_id = result["task_id"]
                print(f"异步任务创建成功，任务ID: {task_id}")
                
                # Poll for subject identification completion
                subject_result = self._poll_task_status(task_id, ak, sk, OMNIHUMAN_RESULT_URL)
                if subject_result and "subject_id" in subject_result:
                    subject_id = subject_result["subject_id"]
                    return (subject_id, f"主体识别成功，ID: {subject_id}")
            
            elif "subject_id" in result:
                # Synchronous response
                subject_id = result["subject_id"]
                return (subject_id, f"主体识别成功，ID: {subject_id}")
            
            print(f"主体识别响应格式异常: {json.dumps(result, indent=2, ensure_ascii=False)}")
            return ("", "主体识别失败: 响应格式异常")
            
        except Exception as e:
            error_msg = f"主体识别过程中发生错误: {e}"
            print(error_msg)
            return ("", error_msg)
    
    def _poll_task_status(self, task_id, ak, sk, base_url, max_attempts=60, delay=5):
        """Poll the API for task status"""
        headers = {
            "Content-Type": "application/json"
        }
        
        # Official polling request body
        if "realman_avatar_picture_create_role_omni" in base_url or "subject" in str(task_id):
            req_key = "realman_avatar_picture_create_role_omni"  # Subject identification
        else:
            req_key = "realman_avatar_picture_omni_v2"  # Video generation
            
        poll_payload = {
            "req_key": req_key,
            "task_id": task_id
        }
        
        signed_headers = sign_request(ak, sk, "POST", base_url, headers, json.dumps(poll_payload))
        print(f"开始轮询任务 {task_id} 状态，最多轮询 {max_attempts} 次，每 {delay} 秒一次")
        
        for attempt in range(max_attempts):
            try:
                response = requests.post(base_url, headers=signed_headers, json=poll_payload)
                response.raise_for_status()
                result = response.json()
                
                print(f"轮询第 {attempt + 1} 次，状态: {result.get('data', {}).get('status', 'unknown')}")
                
                data = result.get("data", {})
                status = data.get("status")
                
                if status == "done":
                    print(f"任务 {task_id} 完成")
                    if req_key == "realman_avatar_picture_create_role_omni":
                        # Subject identification - parse resp_data
                        resp_data = data.get("resp_data", "{}")
                        try:
                            resp_json = json.loads(resp_data)
                            if resp_json.get("status") == 1:  # Contains human subject
                                return {"subject_id": task_id}  # Use task_id as subject_id
                        except:
                            pass
                        return None
                    else:
                        # Video generation - return video_url
                        return data.get("video_url")
                elif status == "failed":
                    print(f"任务 {task_id} 失败")
                    return None
                elif status in ["in_queue", "generating"]:
                    if attempt % 6 == 0:  # Print every 30 seconds
                        print(f"处理中... 状态: {status}")
                    
                time.sleep(delay)
            except Exception as e:
                print(f"轮询第 {attempt + 1} 次失败: {str(e)}")
                time.sleep(delay)
        
        print(f"任务 {task_id} 超时")
        return None


class OmniHumanVideoGenerator:
    """
    ComfyUI node to generate human videos using OmniHuman API with a pre-identified subject ID
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "subject_image": ("IMAGE",),  # Image input for video generation
                "subject_id": ("STRING", {"default": ""}),
                "reference_audio": ("AUDIO",),
                "model": (OMNIHUMAN_MODELS, {"default": "omnihuman-v1.0-standard"}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (["512x512", "768x768", "1024x1024"], {"default": "768x768"}),
                "duration": ("FLOAT", {"default": 3.0, "min": 1.0, "max": 10.0, "step": 0.1}),
                "motion_intensity": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.1}),
                "facial_expression": ("BOOLEAN", {"default": True}),
                "body_movement": ("BOOLEAN", {"default": True}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
            },
            "optional": {
                "background_image": ("IMAGE",),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("视频路径",)
    FUNCTION = "generate_video"
    CATEGORY = "火山引擎 OmniHuman"
    
    def generate_video(self, subject_image, subject_id, reference_audio, model, prompt, resolution, 
                      duration, motion_intensity, facial_expression, body_movement, seed, 
                      background_image=None):
        """Generate video from subject identification result"""
        try:
            print(f"开始OmniHuman视频生成")
            
            # Upload subject image to get URL
            subject_image_path = save_image_for_api(subject_image, f"omnihuman_subject_{uuid.uuid4()}.png")
            subject_image_url = get_image_url(subject_image_path)
            print(f"主体图片已上传: {subject_image_url}")

            ak, sk = load_ak_sk()
            if not ak or not sk:
                return ("ERROR: 无法加载AK/SK",)
            
            headers = {
                "Content-Type": "application/json"
            }
            
            # Official API request body structure for video generation
            # First, handle audio upload if it's a file path
            if reference_audio:
                audio_path = save_audio_for_api(reference_audio, f"omnihuman_audio_{uuid.uuid4()}.wav")
                audio_url = get_audio_url(audio_path)
            else:
                return (None, "错误：音频文件是必需的")
                
            payload = {
                "req_key": "realman_avatar_picture_omni_v2",
                "image_url": subject_image_url,  # Use uploaded image URL
                "audio_url": audio_url
            }
            
            signed_headers = sign_request(ak, sk, "POST", OMNIHUMAN_SUBMIT_URL, headers, json.dumps(payload))
            
            print(f"发送视频生成请求到: {OMNIHUMAN_SUBMIT_URL}")
            print(f"请求头: {signed_headers}")
            print(f"请求体: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            response = requests.post(OMNIHUMAN_SUBMIT_URL, headers=signed_headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            if "task_id" in result:
                task_id = result["task_id"]
                print(f"视频生成任务创建成功，任务ID: {task_id}")
                
                # Poll for video generation completion
                video_url = self._poll_task_status(task_id, ak, sk, OMNIHUMAN_RESULT_URL)
                if video_url:
                    # Download the generated video
                    output_filename = f"omnihuman_video_{uuid.uuid4()}.mp4"
                    output_path = os.path.join(OMNIHUMAN_OUTPUT_DIR, output_filename)
                    
                    if self._download_video(video_url, output_path):
                        return (output_path,)
            
            elif "video_url" in result:
                # Synchronous response with direct video URL
                video_url = result["video_url"]
                output_filename = f"omnihuman_video_{uuid.uuid4()}.mp4"
                output_path = os.path.join(OMNIHUMAN_OUTPUT_DIR, output_filename)
                
                if self._download_video(video_url, output_path):
                    return (output_path,)
            
            return ("ERROR: 视频生成失败",)
            
        except Exception as e:
            error_msg = f"视频生成过程中发生错误: {e}"
            print(error_msg)
            return (f"ERROR: {str(e)}",)
    
    def _poll_task_status(self, task_id, ak, sk, base_url, max_attempts=60, delay=5):
        """Poll the API for task status"""
        headers = {
            "Content-Type": "application/json"
        }
        
        # Official polling request body
        if "realman_avatar_picture_create_role_omni" in base_url or "subject" in str(task_id):
            req_key = "realman_avatar_picture_create_role_omni"  # Subject identification
        else:
            req_key = "realman_avatar_picture_omni_v2"  # Video generation
            
        poll_payload = {
            "req_key": req_key,
            "task_id": task_id
        }
        
        signed_headers = sign_request(ak, sk, "POST", base_url, headers, json.dumps(poll_payload))
        print(f"开始轮询任务 {task_id} 状态，最多轮询 {max_attempts} 次，每 {delay} 秒一次")
        
        for attempt in range(max_attempts):
            try:
                response = requests.post(base_url, headers=signed_headers, json=poll_payload)
                response.raise_for_status()
                result = response.json()
                
                print(f"轮询第 {attempt + 1} 次，状态: {result.get('data', {}).get('status', 'unknown')}")
                
                data = result.get("data", {})
                status = data.get("status")
                
                if status == "done":
                    print(f"任务 {task_id} 完成")
                    if req_key == "realman_avatar_picture_create_role_omni":
                        # Subject identification - parse resp_data
                        resp_data = data.get("resp_data", "{}")
                        try:
                            resp_json = json.loads(resp_data)
                            if resp_json.get("status") == 1:  # Contains human subject
                                return {"subject_id": task_id}  # Use task_id as subject_id
                        except:
                            pass
                        return None
                    else:
                        # Video generation - return video_url
                        return data.get("video_url")
                elif status == "failed":
                    print(f"任务 {task_id} 失败")
                    return None
                elif status in ["in_queue", "generating"]:
                    if attempt % 6 == 0:  # Print every 30 seconds
                        print(f"处理中... 状态: {status}")
                    
                time.sleep(delay)
            except Exception as e:
                print(f"轮询第 {attempt + 1} 次失败: {str(e)}")
                time.sleep(delay)
        
        print(f"任务 {task_id} 超时")
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
OMNIHUMAN_NODE_CLASS_MAPPINGS = {
    "OmniHumanSubjectIdentifier": OmniHumanSubjectIdentifier,
    "OmniHumanVideoGenerator": OmniHumanVideoGenerator
}

# Display names for nodes
OMNIHUMAN_NODE_DISPLAY_NAME_MAPPINGS = {
    "OmniHumanSubjectIdentifier": "火山引擎 OmniHuman 主体识别",
    "OmniHumanVideoGenerator": "火山引擎 OmniHuman 视频生成"
}

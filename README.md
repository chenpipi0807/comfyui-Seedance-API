# Seedance API for ComfyUI

ComfyUI节点，用于调用豆包图生视频API（Seedance）。

![image](https://github.com/user-attachments/assets/333af984-a162-40a2-bd04-854f83073d93)


## API密钥设置

### 豆包API密钥
1. 在[火山引擎](https://console.volcengine.com/auth/login?redirectURI=%2Fark%2Fregion%3Aark%2Bcn-beijing%2Fexperience%2Fvision%3FprojectName%3Ddefault)注册并申请Seedance API访问权限
2. 获取API密钥后，将其填入`API-KEY.txt`文件中

### ImgBB密钥（用于图片上传）
1. 在[ImgBB官网](https://imgbb.com/signup)注册账号
2. 在[API页面](https://api.imgbb.com/)获取API密钥
3. 将ImgBB API密钥填入`IMGBB-KEY.txt`文件中

### 模型简单说明
pro不支持首尾帧， lite支持首尾帧
pro不支持720p， lite支持720p

## 使用方法
1. 准备起始帧图像（必须）和结束帧图像（可选）
2. 设置参数：模型、提示词、分辨率、时长、固定镜头、种子值
3. 运行节点，等待视频生成完成
4. 输出的视频将保存在ComfyUI的output/seedance目录中

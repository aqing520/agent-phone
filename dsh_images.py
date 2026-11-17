"""Bounded inline image validation for DeepSeek ACP prompts."""
import base64
import binascii

MAX_IMAGES = 4
MAX_BYTES = 3 * 1024 * 1024

def validate_images(images):
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError('最多选择 4 张图片')
    result = []
    for image in images:
        if not isinstance(image, dict):
            raise ValueError('图片格式无效')
        mime, data = image.get('mimeType'), image.get('data')
        if mime not in ('image/png', 'image/jpeg', 'image/webp', 'image/gif') or not isinstance(data, str) or len(data) > MAX_BYTES * 4 // 3:
            raise ValueError('图片格式不支持或超过 3 MB')
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('图片编码无效')
        actual = ('image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
                  'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else
                  'image/gif' if raw.startswith((b'GIF87a', b'GIF89a')) else
                  'image/webp' if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP' else None)
        if actual != mime or not raw or len(raw) > MAX_BYTES or base64.b64encode(raw).decode() != data:
            raise ValueError('图片内容与格式不匹配')
        result.append({'type':'image', 'mimeType':mime, 'data':data})
    return result

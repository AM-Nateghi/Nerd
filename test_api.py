"""
اسکریپت تست API های Nerd Server
"""
import requests
import base64
import json
from pathlib import Path

# آدرس سرور
BASE_URL = "http://localhost:8000"


def test_health():
    """تست health check"""
    print("🔍 تست Health Check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"✅ وضعیت: {response.status_code}")
    print(f"📝 پاسخ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print("-" * 50)


def test_upload_image(image_path: str):
    """تست آپلود تصویر"""
    print(f"📤 تست آپلود تصویر: {image_path}")
    
    # خواندن تصویر و تبدیل به base64
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
        base64_image = f"data:image/png;base64,{image_data}"
    
    # ارسال درخواست
    response = requests.post(
        f"{BASE_URL}/api/upload-image",
        json={"image": base64_image}
    )
    
    print(f"✅ وضعیت: {response.status_code}")
    result = response.json()
    print(f"📝 URL تصویر: {result.get('url')}")
    print(f"🆔 ID: {result.get('id')}")
    print("-" * 50)
    
    return result.get("url")


def test_chat_text_only():
    """تست چت با متن ساده"""
    print("💬 تست چت (فقط متن)...")
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "سلام! چطوری؟ به فارسی جواب بده."
                }
            ],
            "model": "gemma3n-e4b"
        }
    )
    
    print(f"✅ وضعیت: {response.status_code}")
    result = response.json()
    print(f"📝 پاسخ: {result['message']['content']}")
    print(f"⏱️ مدت زمان: {result.get('duration_seconds', 0):.2f}s")
    print("-" * 50)


def test_chat_with_image(image_url: str):
    """تست چت با تصویر"""
    print(f"🖼️ تست چت با تصویر...")
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "این تصویر چیه؟ به فارسی توضیح بده."},
                        {"type": "image", "url": image_url}
                    ]
                }
            ],
            "model": "gemma3n-e4b"
        }
    )
    
    print(f"✅ وضعیت: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"📝 پاسخ: {result['message']['content']}")
        print(f"⏱️ مدت زمان: {result.get('duration_seconds', 0):.2f}s")
    else:
        print(f"❌ خطا: {response.text}")
    
    print("-" * 50)


def main():
    print("=" * 50)
    print("🧪 شروع تست API های Nerd Server")
    print("=" * 50)
    print()
    
    try:
        # تست 1: Health Check
        test_health()
        
        # تست 2: چت ساده
        test_chat_text_only()
        
        # تست 3: آپلود تصویر (اختیاری - اگر فایل تصویر دارید)
        # image_path = "path/to/your/image.png"
        # if Path(image_path).exists():
        #     image_url = test_upload_image(image_path)
        #     
        #     # تست 4: چت با تصویر
        #     test_chat_with_image(f"{BASE_URL}{image_url}")
        
        print("✅ همه تست‌ها با موفقیت انجام شد!")
        
    except requests.exceptions.ConnectionError:
        print("❌ خطا: نمی‌توان به سرور متصل شد.")
        print("💡 مطمئن شوید سرور در حال اجراست: python app.py")
    
    except Exception as e:
        print(f"❌ خطای غیرمنتظره: {e}")


if __name__ == "__main__":
    main()

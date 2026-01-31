# utils.py
import base64
import io
import asyncio
from PIL import Image

def compress_image_worker(file_bytes):
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        img.thumbnail((800, 800), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=50) 
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"Worker Error: {e}")
        return None

async def process_multiple_images(files_list):
    if not files_list: return []
    loop = asyncio.get_event_loop()
    tasks = []
    
    for f in files_list:
        if f and f.filename != '':
            # FIX: Remove 'await'. Quart's f.read() returns bytes directly.
            file_bytes = f.read() 
            if file_bytes:
                tasks.append(loop.run_in_executor(None, compress_image_worker, file_bytes))
    
    if not tasks: return []
    return [img for img in await asyncio.gather(*tasks) if img]
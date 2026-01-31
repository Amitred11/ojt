import base64
import io
import asyncio
from PIL import Image

def compress_image(file_storage):
    """Resizes and compresses image to keep DB light and fast."""
    if not file_storage: return None
    try:
        # Use .stream for Quart/Flask file objects
        img = Image.open(file_storage.stream)
        if img.mode in ("RGBA", "P"): 
            img = img.convert("RGB")
        
        # Resize to max 1024px width/height
        img.thumbnail((1024, 1024))
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=70, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"Compression Error: {e}")
        return None

async def process_multiple_images(files_list):
    """Processes multiple images in parallel using threads."""
    loop = asyncio.get_event_loop()
    # Run CPU-bound compression in a thread pool
    tasks = [loop.run_in_executor(None, compress_image, f) for f in files_list if f.filename]
    results = await asyncio.gather(*tasks)
    return [img for img in results if img]
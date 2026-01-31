import base64
import io
import asyncio
from PIL import Image

def compress_image(file_storage):
    """
    Resizes and aggressively compresses image using WebP.
    WebP is significantly smaller than JPEG for DB storage.
    """
    if not file_storage or not file_storage.filename: 
        return None
    try:
        # Load image
        img = Image.open(file_storage.stream)
        
        # 1. Convert to RGB (removes transparency/alpha channel to save space)
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        # 2. Resize to a smaller maximum (800px is plenty for log proof)
        # This significantly reduces the number of pixels stored
        img.thumbnail((800, 800), Image.Resampling.LANCZOS)
        
        # 3. Save to WebP (Superior compression over JPEG)
        buffer = io.BytesIO()
        # Quality 50-60 is the "sweet spot" for database storage
        img.save(buffer, format="WEBP", quality=50, method=6) 
        
        # 4. Convert to Base64
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"Compression Error: {e}")
        return None

async def process_multiple_images(files_list):
    """Processes multiple images in parallel."""
    if not files_list:
        return []
        
    loop = asyncio.get_event_loop()
    # Filter out empty file uploads before processing
    valid_files = [f for f in files_list if f.filename != '']
    
    if not valid_files:
        return []

    tasks = [loop.run_in_executor(None, compress_image, f) for f in valid_files]
    results = await asyncio.gather(*tasks)
    return [img for img in results if img]
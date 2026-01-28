import io
from PIL import Image

def process_transparency(image_data: bytes, threshold: int = 30, remove_white: bool = True) -> bytes:
    """
    Process an image to make the background transparent.
    
    Args:
        image_data: Raw bytes of the image/uploaded file.
        threshold: Color threshold. Pixels darker than this (or brighter if remove_white) become transparent.
        remove_white: If True, remove white/bright backgrounds. If False, remove black/dark backgrounds.
                      Defaults to True as white backgrounds are more common for logos.
                      
    Returns:
        bytes: The processed PNG image bytes.
    """
    try:
        img = Image.open(io.BytesIO(image_data))
        img = img.convert("RGBA")
        
        datas = img.getdata()
        new_data = []
        
        for item in datas:
            # item is (R, G, B, A)
            r, g, b = item[0], item[1], item[2]
            
            is_transparent = False
            
            if remove_white:
                # Remove Bright Pixels (White Backgrounds)
                # Check if it's very bright (considering threshold as distance from 255)
                # e.g. if threshold is 30, anything > 225 is transparent
                limit = 255 - threshold
                if r > limit and g > limit and b > limit:
                    is_transparent = True
            else:
                # Remove Dark Pixels (Black Backgrounds - logic from original script)
                if r < threshold and g < threshold and b < threshold:
                    is_transparent = True
            
            if is_transparent:
                new_data.append((255, 255, 255, 0)) # Fully Transparent
            else:
                new_data.append(item)
                
        img.putdata(new_data)
        
        # Crop tight to content
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
            
        output = io.BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()
        
    except Exception as e:
        print(f"Error processing transparency: {e}")
        # Return original if processing fails
        return image_data

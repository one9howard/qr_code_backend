from PIL import Image
import sys
import os

# New source path (x-height corrected)
SOURCE_PATH = r"C:\Users\player1\.gemini\antigravity\brain\a0e8895b-d227-49df-80e7-4a95acee5a43\insite_logo_xheight_black_1769513447276.png"
DEST_PATH = r"c:\Users\player1\Desktop\InSite_signs\static\img\logo.png"

def process_logo(src, dest):
    print(f"Processing {src} -> {dest}")
    
    try:
        img = Image.open(src)
        img = img.convert("RGBA")
        
        datas = img.getdata()
        new_data = []
        
        # Tolerance for black (simple threshold)
        # Any pixel DARKER than this will be transparent
        limit = 30 
        
        for item in datas:
            # item is (R, G, B, A)
            # If R, G, and B are all very dark
            if item[0] < limit and item[1] < limit and item[2] < limit:
                new_data.append((0, 0, 0, 0)) # Fully Transparent
            else:
                new_data.append(item)
                
        img.putdata(new_data)
        
        # Crop tight to content
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
            print(f"Cropped to {bbox}")
            
        img.save(dest, "PNG")
        print("Success!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    process_logo(SOURCE_PATH, DEST_PATH)

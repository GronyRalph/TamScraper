import os
import sys
import shutil
import re
import xml.etree.ElementTree as ET
from glob import glob

try:
    from PIL import Image, ImageOps
    # Pillow 10+ uses Image.Resampling.LANCZOS, older versions use Image.ANTIALIAS
    RESAMPLE_FILTER = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS
except ImportError:
    print("CRITICAL ERROR: This script requires the Pillow library.")
    print("Please install it: pip install Pillow")
    input("Press Enter to exit...")
    sys.exit(1)

# Configuration
TARGET_RES_FANART = (1280, 720) # 16:9, Black BG, Right Align
TARGET_RES_COVER = (512, 512)   # Max dimension constraint
TARGET_RES_LOGO = (512, 256)    # Max dimension constraint
IMG_QUALITY = 80

def sanitize_lb_title(title):
    if not title: return ""
    return re.sub(r'[<>:"/\\|?*\'`]', '_', title)

def find_image(base_dir, type_folder, title_sanitized, rom_filename_no_ext):
    search_root = os.path.join(base_dir, type_folder)
    if not os.path.exists(search_root): return None
    
    candidates = [
        f"{title_sanitized}-01", f"{title_sanitized}",
        f"{rom_filename_no_ext}-01", title_sanitized.replace('_', ' ')
    ]
    
    valid_exts = {'.jpg', '.png', '.jpeg', '.gif'}
    for root, _, files in os.walk(search_root):
        for file in files:
            name, ext = os.path.splitext(file)
            if ext.lower() in valid_exts and name in candidates:
                return os.path.join(root, file)
    return None

def process_image_cover(source_path, dest_path):
    try:
        img = Image.open(source_path)
        img = ImageOps.exif_transpose(img)
        if img.mode != 'RGB': img = img.convert('RGB')
        
        img.thumbnail(TARGET_RES_COVER, RESAMPLE_FILTER)
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        img.save(dest_path, "JPEG", quality=IMG_QUALITY, optimize=True)
        return True
    except Exception as e:
        print(f"Error processing cover {source_path}: {e}")
        return False

def process_image_fanart(source_path, dest_path):
    try:
        img = Image.open(source_path)
        img = ImageOps.exif_transpose(img)
        if img.mode != 'RGB': img = img.convert('RGB')

        # Crop to 16:9 (Fit)
        # ImageOps.fit resizes and crops to fill the target resolution
        # This effectively zooms in to fill the screen, cropping edges as needed
        img = ImageOps.fit(img, TARGET_RES_FANART, method=RESAMPLE_FILTER, centering=(0.5, 0.5))
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        img.save(dest_path, "JPEG", quality=IMG_QUALITY, optimize=True)
        return True
    except Exception as e:
        print(f"Error processing fanart {source_path}: {e}")
        return False

def process_image_marquee(source_path, dest_path):
    try:
        img = Image.open(source_path)
        img.thumbnail(TARGET_RES_LOGO, RESAMPLE_FILTER)
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        img.save(dest_path, "PNG", optimize=True)
        return True
    except Exception as e:
        print(f"Error processing marquee {source_path}: {e}")
        return False

def get_launchbox_xml(directory):
    for f in glob(os.path.join(directory, "*.xml")):
        if not f.lower().endswith("gamelist.xml"):
            return f
    return None

def process_directory(directory_name):
    full_dir_path = os.path.abspath(directory_name)
    lb_xml = get_launchbox_xml(full_dir_path)
    if not lb_xml: return

    print(f"Processing: {directory_name} (found {os.path.basename(lb_xml)})")
    
    try:
        tree = ET.parse(lb_xml)
        root = tree.getroot()
    except Exception as e:
        print(f"  XML Error: {e}")
        return

    rom_map = {}
    for game in root.findall('Game'):
        app_path = game.find('ApplicationPath')
        if app_path is not None and app_path.text:
            rom_map[os.path.basename(app_path.text)] = game
        # Fallback: map by Title if AppPath missing? 
        # LaunchBox XML usually has correct AppPath relative or absolute.
        # We'll stick to filename matching for safety.

    new_root = ET.Element("gameList")
    game_exts = {'.chd', '.n64', '.z64', '.v64', '.gdi', '.cdi', '.iso', '.cue', '.bin', '.img', '.mdf', '.pbp'}
    
    files = sorted([f for f in os.listdir(full_dir_path) if os.path.isfile(os.path.join(full_dir_path, f))])
    
    count = 0
    for f in files:
        name, ext = os.path.splitext(f)
        if ext.lower() not in game_exts: continue

        print(f"  Game: {name}", end='\r')
        
        game_elem = ET.SubElement(new_root, "game")
        ET.SubElement(game_elem, "path").text = f"./{f}"
        
        # Metadata
        title_text = name
        game_node = rom_map.get(f)
        
        if game_node is not None:
            title = game_node.find("Title")
            if title is not None: title_text = title.text
            ET.SubElement(game_elem, "name").text = title_text
            
            desc = game_node.find("Notes")
            if desc is not None: ET.SubElement(game_elem, "desc").text = desc.text
            
            for tag in ["Developer", "Publisher", "Genre", "MaxPlayers"]:
                node = game_node.find(tag)
                if node is not None and node.text:
                    ET.SubElement(game_elem, tag.lower()).text = node.text
            
            rel = game_node.find("ReleaseDate")
            if rel is not None and rel.text and len(rel.text)>=10:
                ET.SubElement(game_elem, "releasedate").text = rel.text[:10].replace("-", "") + "T000000"

            # Image Finding & Processing
            sanitized = sanitize_lb_title(title_text)
            rom_base = os.path.splitext(f)[0] # Rom Filename without ext for destination uniqueness
            
            # 1. Front (Cover) -> ./images/covers/
            src = find_image(full_dir_path, "Front", sanitized, name)
            if src:
                dest_rel = f"./images/covers/{rom_base}.jpg"
                dest_abs = os.path.join(full_dir_path, "images", "covers", f"{rom_base}.jpg")
                if process_image_cover(src, dest_abs):
                    ET.SubElement(game_elem, "image").text = dest_rel

            # 2. Screenshot (Fanart) -> ./images/fanart/
            src = find_image(full_dir_path, "Screenshot", sanitized, name)
            if src:
                dest_rel = f"./images/fanart/{rom_base}.jpg"
                dest_abs = os.path.join(full_dir_path, "images", "fanart", f"{rom_base}.jpg")
                if process_image_fanart(src, dest_abs):
                    ET.SubElement(game_elem, "fanart").text = dest_rel

            # 3. Clear Logo (Marquee) -> ./images/marquees/
            src = find_image(full_dir_path, "Clear Logo", sanitized, name)
            if src:
                dest_rel = f"./images/marquees/{rom_base}.png"
                dest_abs = os.path.join(full_dir_path, "images", "marquees", f"{rom_base}.png")
                if process_image_marquee(src, dest_abs):
                    ET.SubElement(game_elem, "marquee").text = dest_rel
        
        else:
            # Minimal entry if no metadata
            ET.SubElement(game_elem, "name").text = name

        count += 1

    # Save XML
    output_path = os.path.join(full_dir_path, "gamelist.xml")
    try:
        ET.indent(new_root, space="  ", level=0)
    except AttributeError:
        pass 
    
    ET.ElementTree(new_root).write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"\n  Generated {os.path.basename(output_path)} with {count} games.")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_dir)
    
    # Scan all subdirectories
    dirs = [d for d in os.listdir('.') if os.path.isdir(d)]
    excludes = {'System Volume Information', '$RECYCLE.BIN', 'images', 'Config'}
    
    print("TamScraper v2.0 - Starting Universal Scan...")
    
    found = 0
    for d in dirs:
        if d in excludes or d.startswith('.'): continue
        if get_launchbox_xml(os.path.abspath(d)):
            process_directory(d)
            found += 1
            
    if found == 0:
        print("No folders with LaunchBox XML found.")
    
    print("Done.")
    input("Press Enter to close...")

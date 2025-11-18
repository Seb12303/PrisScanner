import os
from pathlib import Path
import pytesseract
from PIL import Image
from io import BytesIO
import requests
from fuzzywuzzy import fuzz
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil

# === CONFIG ===
stores = [
    "bunnpris", "coop-extra", "coop-mega", "coop-prix",
    "joker", "kiwi", "meny", "rema-1000", "spar", "europris", 
    "gigaboks", "matkroken"
]

search_terms = ["battery", "red bull", "monster", "powerking", "burn", "powerade", "redbull", "trst"]
#search_terms = ["protein", "barebells"]
# === Advanced Config ===


#Percentage of string that matches keyword to create a matcgh
FUZZY_THRESHOLD = 80

MAX_THREADS = 5

base_url = "https://mattilbud.no/kundeaviser/{}-no"
download_dir = Path("catalog_images")
download_dir.mkdir(exist_ok=True)


#Wipes the hits folder before a run incase of old hits (kjipt å gå etter tilbud som ikke finnes lenger)
hits_dir = Path("hits")
hits_dir.mkdir(exist_ok=True)
shutil.rmtree(hits_dir)
hits_dir = Path("hits")
hits_dir.mkdir(exist_ok=True)


# === FUNCTIONS ===
def download_image(url, path):
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content))
    img.save(path)
    return path

def check_image_for_terms(image_path, terms):
    text = pytesseract.image_to_string(Image.open(image_path))
    text_lower = text.lower()
    for term in terms:
        if fuzz.partial_ratio(term.lower(), text_lower) >= FUZZY_THRESHOLD:
            return term
    return None

def process_image(store, idx, src):
    ext = ".png"
    if ".webp" in src.lower():
        ext = ".webp"
    elif ".jpg" in src.lower() or ".jpeg" in src.lower():
        ext = ".jpg"

    img_name = f"{store}_img{idx}{ext}"
    img_path = download_dir / img_name
    try:
        resp = requests.get(src, timeout=15)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        img.save(img_path)

        matched_term = check_image_for_terms(img_path, search_terms)
        if matched_term:
            # Move to hits dir at same level
            hit_path = hits_dir / img_name
            img_path.replace(hit_path)
            print(f"[HIT] {img_name} (matched: {matched_term})")
            return store, img_name, matched_term
    except Exception as e:
        print(f"Failed {img_name}: {e}")
    return None

# === MAIN SCRAPER ===
hits = []

with sync_playwright() as p:
    browser = p.firefox.launch(headless=True)
    page = browser.new_page()

    for store in stores:
        url = base_url.format(store)
        print(f"=== Fetching {store} ===")
        page.goto(url)
        page.wait_for_selector("img", timeout=10000)
        images = page.query_selector_all("img")
        print(f"Found {len(images)} images on page")

        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = [executor.submit(process_image, store, idx+1, img.get_attribute("src"))
                       for idx, img in enumerate(images) if img.get_attribute("src")]
            for f in as_completed(futures):
                result = f.result()
                if result:
                    hits.append(result)

    browser.close()

# Optional: summary of hits
print(f"\nDone. Total hits saved: {len(hits)}")
print(hits)

# Delete catalog folder when done
if download_dir.exists():
    shutil.rmtree(download_dir)
import os
import random
import requests
import shutil
from xml.etree import ElementTree as ET

addon_id = "resource.images.skinbackgrounds.xonfluenceduncanbuild"
base_path = os.path.join(addon_id)
image_save_path = os.path.join(base_path, "resources")
addon_xml_path = os.path.join(base_path, "addon.xml")
zip_dir = os.path.join("zips", addon_id)

# Exclude images a.jpg to k.jpg from deletion
exclude_images = [f"{chr(c)}.jpg" for c in range(ord("a"), ord("k") + 1)]

def delete_images():
    if not os.path.exists(image_save_path):
        os.makedirs(image_save_path)
    for filename in os.listdir(image_save_path):
        if filename not in exclude_images:
            filepath = os.path.join(image_save_path, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
                print(f"Deleted {filename}")

def download_picsum_images(count=7):
    for i in range(count):
        url = f"https://picsum.photos/3840/2160.jpg?random={random.randint(1000, 9999)}"
        filename = f"picsum_{i}.jpg"
        filepath = os.path.join(image_save_path, filename)
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(filepath, "wb") as f:
                shutil.copyfileobj(response.raw, f)
            print(f"Downloaded Picsum: {filename}")
        else:
            print(f"Failed to download {url}")

def download_postimg_images(txt_path="postimg_urls.txt", count=7):
    if not os.path.exists(txt_path):
        print("Missing postimg_urls.txt file.")
        return
    with open(txt_path, "r") as f:
        urls = [line.strip() for line in f if line.strip()]
    selected = random.sample(urls, min(count, len(urls)))
    for i, url in enumerate(selected):
        ext = os.path.splitext(url)[-1].split("?")[0]
        filename = f"postimg_{i}{ext}"
        filepath = os.path.join(image_save_path, filename)
        try:
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    shutil.copyfileobj(response.raw, f)
                print(f"Downloaded Postimg: {filename}")
            else:
                print(f"Failed: {url}")
        except Exception as e:
            print(f"Error downloading {url}: {e}")

def bump_version():
    tree = ET.parse(addon_xml_path)
    root = tree.getroot()
    old_version = root.attrib["version"]
    parts = old_version.strip().split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    new_version = ".".join(parts)
    root.set("version", new_version)
    tree.write(addon_xml_path, encoding="UTF-8", xml_declaration=True)
    print(f"Version bumped: {old_version} → {new_version}")
    return new_version

def cleanup_old_zips(current_version):
    if not os.path.exists(zip_dir):
        return
    current_zip = f"{addon_id}-{current_version}.zip"
    for fname in os.listdir(zip_dir):
        if fname.endswith(".zip") and fname != current_zip:
            os.remove(os.path.join(zip_dir, fname))
            print(f"Deleted old zip: {fname}")

def main():
    delete_images()
    download_picsum_images()
    download_postimg_images()
    new_version = bump_version()

    # Generate new zip and addons.xml/md5
    print("Running repo_xml_generator_py3.py...")
    os.system("python repo_xml_generator_py3.py")

    # Remove old zips
    cleanup_old_zips(new_version)

if __name__ == "__main__":
    main()

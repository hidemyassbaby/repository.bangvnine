import os
import requests
import shutil
from xml.etree import ElementTree as ET

# Paths
addon_id = "resource.images.skinbackgrounds.xonfluenceduncanbuild"
base_path = os.path.join(addon_id)
image_save_path = os.path.join(base_path, "resources")
addon_xml_path = os.path.join(base_path, "addon.xml")
zip_dir = os.path.join("zips", addon_id)

# Images to keep
exclude_images = [
    "a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg",
    "f.jpg", "g.jpg", "h.jpg", "i.jpg", "j.jpg", "k.jpg"
]

def delete_images():
    if not os.path.exists(image_save_path):
        os.makedirs(image_save_path)
    for filename in os.listdir(image_save_path):
        if filename not in exclude_images:
            filepath = os.path.join(image_save_path, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
                print(f"Deleted {filename}")

def download_images():
    for i in range(8):
        url = f"https://picsum.photos/3840/2160.jpg?random={i}"
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            filename = f"background_{i}.jpg"
            filepath = os.path.join(image_save_path, filename)
            with open(filepath, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            print(f"Downloaded {filename}")
        else:
            print(f"Failed to download image {i}")

def bump_version():
    tree = ET.parse(addon_xml_path)
    root = tree.getroot()
    old_version = root.attrib["version"]
    parts = old_version.strip().split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    new_version = ".".join(parts)
    root.set("version", new_version)
    tree.write(addon_xml_path, encoding="UTF-8", xml_declaration=True)
    print(f"Bumped version: {old_version} → {new_version}")
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
    download_images()
    new_version = bump_version()
    cleanup_old_zips(new_version)

if __name__ == "__main__":
    main()

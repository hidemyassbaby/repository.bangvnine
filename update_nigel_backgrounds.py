import os
import requests
import shutil
from xml.etree import ElementTree as ET

base_path = "resource.images.skinbackgrounds.xonfluencenigelbuild"
image_save_path = os.path.join(base_path, "resources")
addon_xml_path = os.path.join(base_path, "addon.xml")

exclude_images = [
    "oranzhevyy-fon-nadpis-bang - Copy (2).jpg",
    "oranzhevyy-fon-nadpis-bang - Copy (3).jpg",
    "oranzhevyy-fon-nadpis-bang.jpg",
    "bang-bang-wallpaper-2 - Copy (2).jpg",
    "bang-bang-wallpaper-2 - Copy.jpg",
    "bang-bang-wallpaper-2.jpg",
    "122579146_3542275872526363_5780681884022639449_n.jpg",
    "IMG_7287.jpg",
    "121117_wo.jpg",
    "506021828_1299884798806613_5533992735717483610_n.jpg",
    "QGr5cwa - Imgur.jpg",
    "WZFR5LSQQFC35OWXBZMGWVC6MY.jpg"
]

def delete_images():
    if not os.path.exists(image_save_path):
        os.makedirs(image_save_path)
    for filename in os.listdir(image_save_path):
        if filename not in exclude_images:
            os.remove(os.path.join(image_save_path, filename))

def download_images():
    for i in range(8):
        url = f"https://picsum.photos/3840/2160.jpg?random={i}"
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(os.path.join(image_save_path, f"background_{i}.jpg"), 'wb') as f:
                shutil.copyfileobj(response.raw, f)

def bump_version():
    tree = ET.parse(addon_xml_path)
    root = tree.getroot()
    old_version = root.attrib['version']
    parts = old_version.split('.')
    parts[-1] = str(int(parts[-1]) + 1)
    new_version = '.'.join(parts)
    root.set('version', new_version)
    tree.write(addon_xml_path, encoding="UTF-8", xml_declaration=True)
    print(f"Bumped version from {old_version} to {new_version}")

def main():
    delete_images()
    download_images()
    bump_version()

if __name__ == "__main__":
    main()

import os
import requests
import shutil
from xml.etree import ElementTree as ET

# Define the path to the resources folder and addon.xml file
kodi_addon_repo_path = './'  # This should be the root of your repo
image_save_path = os.path.join(kodi_addon_repo_path, 'repository.bangvnine', 'resource.images.skinbackgrounds.xonfluencenigelbuild', 'resources')
addon_xml_path = os.path.join(kodi_addon_repo_path, 'repository.bangvnine', 'resource.images.skinbackgrounds.xonfluencenigelbuild', 'addon.xml')

# List of images to exclude from deletion
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

# Function to delete all images except the ones in the exclude list
def delete_images():
    for filename in os.listdir(image_save_path):
        file_path = os.path.join(image_save_path, filename)
        if os.path.isfile(file_path) and filename not in exclude_images:
            os.remove(file_path)
            print(f"Deleted {filename}")
        else:
            print(f"Skipped {filename}")

# Define the base URL for random images
image_url_base = 'https://picsum.photos/3840/2160.jpg'

# Define the number of images to download
num_images = 8

# Function to download images from Picsum
def download_image(image_number):
    url = f"{image_url_base}?random={image_number}"
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        image_name = f"background_{image_number}.jpg"
        image_path = os.path.join(image_save_path, image_name)
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        with open(image_path, 'wb') as file:
            shutil.copyfileobj(response.raw, file)
        print(f"Downloaded {image_name} successfully.")
    else:
        print(f"Failed to download image {image_number}.")

# Function to bump the version in addon.xml
def bump_version():
    tree = ET.parse(addon_xml_path)
    root = tree.getroot()

    version = root.attrib['version']
    print(f"Current version: {version}")

    version_parts = version.split('.')
    version_parts[-1] = str(int(version_parts[-1]) + 1)  # Increment patch version
    new_version = '.'.join(version_parts)

    root.attrib['version'] = new_version
    tree.write(addon_xml_path)
    print(f"Updated version to: {new_version}")

# Main execution
def main():
    delete_images()  # Step 1: Delete old images
    for i in range(1, num_images + 1):
        download_image(i)  # Step 2: Download new images
    bump_version()  # Step 3: Bump the version in addon.xml

if __name__ == '__main__':
    main()

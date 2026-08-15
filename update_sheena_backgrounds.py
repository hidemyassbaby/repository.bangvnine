import io
import os
import random
import requests
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps
from xml.etree import ElementTree as ET


addon_id = "resource.images.skinbackgrounds.xonfluencesheena"

base_path = addon_id
image_save_path = os.path.join(base_path, "resources")
addon_xml_path = os.path.join(base_path, "addon.xml")
zip_dir = os.path.join("zips", addon_id)

# 4K UHD television resolution
target_width = 3840
target_height = 2160

# Reject images that are too small to look good on a large TV
minimum_usable_width = 2560
minimum_usable_height = 1440

# Maximum output file size: approximately 2.5 MB
maximum_file_size = 2_500_000

# Never delete these four permanent Kodi backgrounds
protected_images = {
    "a.jpg",
    "b.jpg",
    "c.jpg",
    "d.jpg"
}


def ensure_directories():
    """Create the required Kodi repository folders."""

    os.makedirs(image_save_path, exist_ok=True)
    os.makedirs(zip_dir, exist_ok=True)


def delete_old_downloaded_images():
    """Delete old downloaded images but preserve a.jpg to d.jpg."""

    for filename in os.listdir(image_save_path):
        filepath = os.path.join(image_save_path, filename)

        if filename.lower() in protected_images:
            print(f"Keeping protected image: {filename}")
            continue

        if os.path.isfile(filepath):
            os.remove(filepath)
            print(f"Deleted old image: {filename}")


def usable_16_9_size(width, height):
    """
    Calculate how much of the source image remains after cropping it
    to the television's 16:9 aspect ratio.
    """

    target_ratio = target_width / target_height
    source_ratio = width / height

    if source_ratio > target_ratio:
        usable_height = height
        usable_width = int(height * target_ratio)
    else:
        usable_width = width
        usable_height = int(width / target_ratio)

    return usable_width, usable_height


def optimise_image(image):
    """
    Crop the image to 16:9, resize it to 4K and compress it while
    retaining good quality for large televisions.
    """

    image = ImageOps.exif_transpose(image).convert("RGB")

    source_width, source_height = image.size
    usable_width, usable_height = usable_16_9_size(
        source_width,
        source_height
    )

    print(
        f"Source resolution: {source_width}×{source_height}"
    )

    if (
        usable_width < minimum_usable_width
        or usable_height < minimum_usable_height
    ):
        raise ValueError(
            "The selected image is too small for a sharp large-screen "
            f"background. Usable resolution is "
            f"{usable_width}×{usable_height}; at least "
            f"{minimum_usable_width}×{minimum_usable_height} is required."
        )

    try:
        resampling_method = Image.Resampling.LANCZOS
    except AttributeError:
        resampling_method = Image.LANCZOS

    television_image = ImageOps.fit(
        image,
        (target_width, target_height),
        method=resampling_method,
        centering=(0.5, 0.5)
    )

    # Gradually reduce JPEG quality until the image is below the target size
    quality_levels = [88, 85, 82, 80, 78]

    final_data = None
    final_quality = quality_levels[-1]

    for quality in quality_levels:
        buffer = io.BytesIO()

        television_image.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
            subsampling=2
        )

        final_data = buffer.getvalue()
        final_quality = quality

        if len(final_data) <= maximum_file_size:
            break

    print(
        f"Finished resolution: {target_width}×{target_height}"
    )
    print(
        f"JPEG quality: {final_quality}"
    )
    print(
        f"Finished file size: {len(final_data) / 1_000_000:.2f} MB"
    )

    return final_data


def download_one_random_image(txt_path="postimg_urls.txt"):
    """
    Select and download exactly one random image from postimg_urls.txt.
    The old Kodi background is retained if the new image fails.
    """

    if not os.path.exists(txt_path):
        print(f"Missing file: {txt_path}")
        return False

    with open(txt_path, "r", encoding="utf-8") as file:
        urls = [
            line.strip()
            for line in file
            if line.strip() and not line.strip().startswith("#")
        ]

    if not urls:
        print(f"No image URLs were found in {txt_path}")
        return False

    selected_url = random.choice(urls)

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    temporary_path = None

    try:
        print(f"Downloading one random background: {selected_url}")

        response = requests.get(
            selected_url,
            headers=headers,
            timeout=45
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        if content_type and not content_type.startswith("image/"):
            raise ValueError(
                "The selected URL did not return an image."
            )

        with Image.open(io.BytesIO(response.content)) as downloaded_image:
            optimised_data = optimise_image(downloaded_image)

        # Prepare the completed image before deleting the old background
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".jpg",
            delete=False
        ) as temporary_file:
            temporary_file.write(optimised_data)
            temporary_path = temporary_file.name

        delete_old_downloaded_images()

        final_path = os.path.join(
            image_save_path,
            "random_background.jpg"
        )

        os.replace(temporary_path, final_path)

        print("Saved: random_background.jpg")
        return True

    except (
        requests.RequestException,
        ValueError,
        OSError,
        Image.UnidentifiedImageError
    ) as error:
        print(f"Background download or processing failed: {error}")

        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)

        return False


def bump_version():
    """Increase the final number of the Kodi add-on version."""

    if not os.path.exists(addon_xml_path):
        print(f"Missing file: {addon_xml_path}")
        return None

    tree = ET.parse(addon_xml_path)
    root = tree.getroot()

    old_version = root.attrib.get("version")

    if not old_version:
        print("No version was found in addon.xml")
        return None

    version_parts = old_version.strip().split(".")

    try:
        version_parts[-1] = str(
            int(version_parts[-1]) + 1
        )
    except ValueError:
        print(f"Invalid add-on version: {old_version}")
        return None

    new_version = ".".join(version_parts)
    root.set("version", new_version)

    tree.write(
        addon_xml_path,
        encoding="UTF-8",
        xml_declaration=True
    )

    print(f"Version bumped: {old_version} → {new_version}")
    return new_version


def run_repository_generator():
    """Generate the Kodi repository files and ZIP package."""

    generator_path = "repo_xml_generator_py3.py"

    if not os.path.exists(generator_path):
        print(f"Missing file: {generator_path}")
        return False

    print("Running repo_xml_generator_py3.py...")

    try:
        subprocess.run(
            [sys.executable, generator_path],
            check=True
        )

        print("Kodi repository generated successfully.")
        return True

    except subprocess.CalledProcessError as error:
        print(f"Repository generator failed: {error}")
        return False


def cleanup_old_zips(current_version):
    """Keep only the ZIP matching the new add-on version."""

    if not current_version or not os.path.exists(zip_dir):
        return

    current_zip = f"{addon_id}-{current_version}.zip"

    for filename in os.listdir(zip_dir):
        filepath = os.path.join(zip_dir, filename)

        if (
            filename.lower().endswith(".zip")
            and filename != current_zip
            and os.path.isfile(filepath)
        ):
            os.remove(filepath)
            print(f"Deleted old Kodi ZIP: {filename}")


def main():
    print("Updating Kodi background add-on...")

    ensure_directories()

    # Downloads exactly one random image
    downloaded = download_one_random_image()

    if not downloaded:
        print(
            "Update stopped. The existing Kodi images were not replaced."
        )
        return

    new_version = bump_version()

    if not new_version:
        print("Update stopped because the version could not be changed.")
        return

    repository_created = run_repository_generator()

    if repository_created:
        cleanup_old_zips(new_version)
        print("Kodi background add-on update completed!")


if __name__ == "__main__":
    main()
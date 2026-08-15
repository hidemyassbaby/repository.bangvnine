import io
import os
import random
import requests
import subprocess
import sys
import time

from PIL import Image, ImageOps
from xml.etree import ElementTree as ET


addon_id = "resource.images.skinbackgrounds.xonfluencewaynebuild"

base_path = addon_id
image_save_path = os.path.join(base_path, "resources")
addon_xml_path = os.path.join(base_path, "addon.xml")
zip_dir = os.path.join("zips", addon_id)

# 4K UHD television resolution
target_width = 3840
target_height = 2160

# Maximum compressed image size: approximately 2.5 MB
maximum_file_size = 2_500_000

# Download retry settings
download_attempts = 3
request_timeout = 45

# Protect a.jpg through k.jpg from deletion
exclude_images = {
    f"{chr(letter)}.jpg"
    for letter in range(ord("a"), ord("k") + 1)
}


def ensure_directories():
    """Create the required add-on and ZIP directories."""

    os.makedirs(image_save_path, exist_ok=True)
    os.makedirs(zip_dir, exist_ok=True)


def delete_images():
    """Delete downloaded images but preserve a.jpg through k.jpg."""

    for filename in os.listdir(image_save_path):
        filepath = os.path.join(image_save_path, filename)

        if filename.lower() in exclude_images:
            print(f"Keeping protected image: {filename}")
            continue

        if os.path.isfile(filepath):
            os.remove(filepath)
            print(f"Deleted old image: {filename}")


def compress_image(image_data):
    """
    Convert an image to a sharp 4K 16:9 JPEG and reduce its file size.
    """

    with Image.open(io.BytesIO(image_data)) as source_image:
        source_image = ImageOps.exif_transpose(source_image)
        source_image = source_image.convert("RGB")

        source_width, source_height = source_image.size

        print(
            f"Source resolution: "
            f"{source_width}×{source_height}"
        )

        try:
            resampling_method = Image.Resampling.LANCZOS
        except AttributeError:
            resampling_method = Image.LANCZOS

        # Crop to 16:9 and resize to 4K
        television_image = ImageOps.fit(
            source_image,
            (target_width, target_height),
            method=resampling_method,
            centering=(0.5, 0.5)
        )

        # Reduce quality gradually until the target size is reached
        quality_levels = [
            88,
            85,
            82,
            80,
            78,
            75,
            72
        ]

        final_data = None
        final_quality = quality_levels[-1]

        for quality in quality_levels:
            output = io.BytesIO()

            television_image.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
                subsampling=2
            )

            final_data = output.getvalue()
            final_quality = quality

            if len(final_data) <= maximum_file_size:
                break

        final_size_mb = len(final_data) / 1_000_000

        print(
            f"Compressed resolution: "
            f"{target_width}×{target_height}"
        )

        print(f"JPEG quality: {final_quality}")
        print(f"Compressed size: {final_size_mb:.2f} MB")

        return final_data


def download_and_compress(url, filepath):
    """
    Download an image, retry if necessary, then compress and save it.
    """

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for attempt in range(1, download_attempts + 1):
        try:
            print(
                f"Downloading attempt {attempt} of "
                f"{download_attempts}: {url}"
            )

            response = requests.get(
                url,
                headers=headers,
                timeout=request_timeout
            )

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type",
                ""
            ).lower()

            if (
                content_type
                and not content_type.startswith("image/")
            ):
                raise ValueError(
                    "The URL did not return an image."
                )

            compressed_data = compress_image(
                response.content
            )

            with open(filepath, "wb") as image_file:
                image_file.write(compressed_data)

            print(
                f"Saved compressed image: "
                f"{os.path.basename(filepath)}"
            )

            return True

        except (
            requests.RequestException,
            ValueError,
            OSError,
            Image.UnidentifiedImageError
        ) as error:
            print(f"Download or compression failed: {error}")

            if attempt < download_attempts:
                waiting_time = attempt * 5

                print(
                    f"Waiting {waiting_time} seconds "
                    "before retrying..."
                )

                time.sleep(waiting_time)

    print(f"Unable to download: {url}")
    return False


def download_picsum_images(count=3):
    """Download and compress random Picsum backgrounds."""

    print("")
    print(f"Downloading {count} Picsum backgrounds...")

    successful_downloads = 0
    maximum_attempts = count * 5
    attempted_urls = set()

    while (
        successful_downloads < count
        and len(attempted_urls) < maximum_attempts
    ):
        random_number = random.randint(
            1000,
            999999
        )

        url = (
            "https://picsum.photos/3840/2160.jpg"
            f"?random={random_number}"
        )

        if url in attempted_urls:
            continue

        attempted_urls.add(url)

        filename = (
            f"picsum_{successful_downloads}.jpg"
        )

        filepath = os.path.join(
            image_save_path,
            filename
        )

        downloaded = download_and_compress(
            url,
            filepath
        )

        if downloaded:
            successful_downloads += 1
        else:
            print(
                "Trying another random Picsum image..."
            )

    print(
        f"Picsum images downloaded: "
        f"{successful_downloads} of {count}"
    )

    return successful_downloads


def download_postimg_images(
    txt_path="postimg_urls.txt",
    count=7
):
    """
    Randomly select Postimg URLs and save compressed JPEG versions.
    """

    if not os.path.exists(txt_path):
        print(f"Missing file: {txt_path}")
        return 0

    with open(
        txt_path,
        "r",
        encoding="utf-8"
    ) as file:
        urls = [
            line.strip()
            for line in file
            if line.strip()
            and not line.strip().startswith("#")
        ]

    if not urls:
        print(
            f"No URLs were found in {txt_path}"
        )
        return 0

    # Try URLs in a new random order each time
    random.shuffle(urls)

    required_downloads = min(
        count,
        len(urls)
    )

    successful_downloads = 0

    print("")
    print(
        f"Downloading {required_downloads} "
        "Postimg backgrounds..."
    )

    for url in urls:
        if successful_downloads >= required_downloads:
            break

        filename = (
            f"postimg_{successful_downloads}.jpg"
        )

        filepath = os.path.join(
            image_save_path,
            filename
        )

        downloaded = download_and_compress(
            url,
            filepath
        )

        if downloaded:
            successful_downloads += 1
        else:
            print(
                "Trying another Postimg URL..."
            )

    print(
        f"Postimg images downloaded: "
        f"{successful_downloads} of "
        f"{required_downloads}"
    )

    return successful_downloads


def bump_version():
    """Increase the last number of the add-on version."""

    if not os.path.exists(addon_xml_path):
        print(f"Missing file: {addon_xml_path}")
        return None

    tree = ET.parse(addon_xml_path)
    root = tree.getroot()

    old_version = root.attrib.get("version")

    if not old_version:
        print("No version found in addon.xml")
        return None

    version_parts = old_version.strip().split(".")

    try:
        version_parts[-1] = str(
            int(version_parts[-1]) + 1
        )
    except ValueError:
        print(f"Invalid version: {old_version}")
        return None

    new_version = ".".join(version_parts)

    root.set("version", new_version)

    tree.write(
        addon_xml_path,
        encoding="UTF-8",
        xml_declaration=True
    )

    print(
        f"Version bumped: {old_version} → {new_version}"
    )

    return new_version


def run_repository_generator():
    """Run the Kodi repository generator."""

    generator_path = "repo_xml_generator_py3.py"

    if not os.path.exists(generator_path):
        print(f"Missing file: {generator_path}")
        return False

    print("")
    print("Running repo_xml_generator_py3.py...")

    try:
        subprocess.run(
            [sys.executable, generator_path],
            check=True
        )

        print(
            "Kodi repository generated successfully."
        )

        return True

    except subprocess.CalledProcessError as error:
        print(
            f"Repository generator failed: {error}"
        )

        return False


def cleanup_old_zips(current_version):
    """Keep only the ZIP for the current add-on version."""

    if (
        not current_version
        or not os.path.exists(zip_dir)
    ):
        return

    current_zip = (
        f"{addon_id}-{current_version}.zip"
    )

    for filename in os.listdir(zip_dir):
        filepath = os.path.join(
            zip_dir,
            filename
        )

        if (
            filename.lower().endswith(".zip")
            and filename != current_zip
            and os.path.isfile(filepath)
        ):
            os.remove(filepath)

            print(
                f"Deleted old ZIP: {filename}"
            )


def main():
    """Run the complete Wayne background update."""

    print("Updating Wayne Kodi backgrounds...")

    ensure_directories()
    delete_images()

    picsum_downloads = download_picsum_images(
        count=3
    )

    postimg_downloads = download_postimg_images(
        count=7
    )

    total_downloads = (
        picsum_downloads + postimg_downloads
    )

    if total_downloads == 0:
        print(
            "No images were downloaded. "
            "The repository will not be updated."
        )
        return

    new_version = bump_version()

    if not new_version:
        print(
            "The version could not be updated."
        )
        return

    repository_created = run_repository_generator()

    if repository_created:
        cleanup_old_zips(new_version)

        print("")
        print(
            "Wayne Kodi background update completed!"
        )


if __name__ == "__main__":
    main()
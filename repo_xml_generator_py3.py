"""
Python 3 version of the Kodi addons.xml generator script.
Original by whufclee, updated for Python 3 by ChatGPT.
"""

import re
import os
import shutil
import hashlib
import zipfile

class Generator:
    def __init__(self):
        zips_path = 'zips'
        if not os.path.exists(zips_path):
            os.makedirs(zips_path)

        self._remove_binaries()
        self._generate_addons_file()
        self._generate_md5_file()
        print("Finished updating addons xml and md5 files")

    def Create_Zips(self, addon_id, version):
        xml_path = os.path.join(addon_id, 'addon.xml')
        addon_folder = os.path.join('zips', addon_id)
        if not os.path.exists(addon_folder):
            os.makedirs(addon_folder)

        final_zip = os.path.join('zips', addon_id, f"{addon_id}-{version}.zip")
        if not os.path.exists(final_zip):
            print(f"NEW ADD-ON - Creating zip for: {addon_id} v.{version}")
            with zipfile.ZipFile(final_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
                root_len = len(os.path.dirname(os.path.abspath(addon_id)))
                for root, dirs, files in os.walk(addon_id):
                    archive_root = os.path.abspath(root)[root_len:]
                    for f in files:
                        fullpath = os.path.join(root, f)
                        archive_name = os.path.join(archive_root, f)
                        zipf.write(fullpath, archive_name)

            # Copy icon, fanart, and addon.xml
            copyfiles = ['icon.png', 'fanart.jpg', 'addon.xml']
            files = os.listdir(addon_id)
            for file in files:
                if file in copyfiles:
                    shutil.copy(os.path.join(addon_id, file), addon_folder)

    def _remove_binaries(self):
        for parent, dirnames, filenames in os.walk('.'):
            for fn in filenames:
                if fn.lower().endswith(('pyo', 'pyc')):
                    compiled = os.path.join(parent, fn)
                    py_file = compiled.replace('.pyo', '.py').replace('.pyc', '.py')
                    if os.path.exists(py_file):
                        try:
                            os.remove(compiled)
                            print(f"Removed compiled python file: {compiled}")
                        except Exception as e:
                            print(f"Failed to remove compiled python file: {compiled}\n{e}")
                    else:
                        print(f"Compiled file found but no matching .py file exists: {compiled}")

    def _generate_addons_file(self):
        addons = os.listdir('.')
        addons_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n'

        for addon in addons:
            try:
                if not os.path.isdir(addon) or addon == "zips" or addon.startswith('.'):
                    continue
                _path = os.path.join(addon, "addon.xml")
                with open(_path, "r", encoding="utf-8") as f:
                    xml_lines = f.read().splitlines()
                addon_xml = ""
                ver_found = False
                for line in xml_lines:
                    if "<?xml" in line:
                        continue
                    if 'version="' in line and not ver_found:
                        version = re.search(r'version="(.+?)"', line).group(1)
                        ver_found = True
                    addon_xml += line.rstrip() + "\n"
                addons_xml += addon_xml.rstrip() + "\n\n"

                self.Create_Zips(addon, version)

            except Exception as e:
                print(f"Excluding {_path} due to error: {e}")

        addons_xml = addons_xml.strip() + "\n</addons>\n"
        self._save_file(addons_xml.encode("utf-8"), file=os.path.join('zips', 'addons.xml'))

    def _generate_md5_file(self):
        try:
            with open(os.path.join('zips', 'addons.xml'), 'rb') as f:
                m = hashlib.md5(f.read()).hexdigest()
            self._save_file(m, file=os.path.join('zips', 'addons.xml.md5'))
        except Exception as e:
            print(f"An error occurred creating addons.xml.md5 file!\n{e}")

    def _save_file(self, data, file):
        try:
            mode = 'wb' if isinstance(data, bytes) else 'w'
            with open(file, mode) as f:
                f.write(data)
        except Exception as e:
            print(f"An error occurred saving {file} file!\n{e}")


if __name__ == "__main__":
    Generator()

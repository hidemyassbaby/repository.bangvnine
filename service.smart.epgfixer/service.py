# Smart EPG Fixer: Full updated service.py with IPTV Merge integration

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import os
import datetime
import time

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
PROFILE = xbmc.translatePath(ADDON.getAddonInfo('profile'))
SETTINGS_FILE = os.path.join(PROFILE, 'settings.xml')
LAST_RUN_FILE = os.path.join(PROFILE, 'last_run.txt')
MERGE_FLAG = '_iptv_merge_force_run'

DEFAULT_DAYS = 7
MERGE_PLUGIN_URL = 'plugin://plugin.program.iptv.merge/?_=merge'

if not xbmcvfs.exists(PROFILE):
    xbmcvfs.mkdirs(PROFILE)

monitor = xbmc.Monitor()

def log(msg):
    xbmc.log(f"[{ADDON_NAME}] {msg}", xbmc.LOGNOTICE)

def notify(message):
    xbmcgui.Dialog().notification(ADDON_NAME, message, xbmcgui.NOTIFICATION_INFO, 5000)

def get_last_run():
    if xbmcvfs.exists(LAST_RUN_FILE):
        with xbmcvfs.File(LAST_RUN_FILE) as f:
            content = f.read().decode('utf-8')
            try:
                return datetime.datetime.strptime(content, '%Y-%m-%d')
            except:
                return None
    return None

def set_last_run():
    with xbmcvfs.File(LAST_RUN_FILE, 'w') as f:
        f.write(datetime.datetime.now().strftime('%Y-%m-%d'))

def epg_cleanup():
    epg_path = xbmc.translatePath("special://userdata/Database/Epg11.db")
    if xbmcvfs.exists(epg_path):
        xbmcvfs.delete(epg_path)
        log("Deleted EPG database.")
    else:
        log("No EPG database found to delete.")

def wait_for_pvr():
    timeout = 60
    log("Waiting for PVR to load channels...")
    while timeout > 0:
        if xbmc.getCondVisibility('Pvr.HasTVChannels'):
            log("PVR channels detected.")
            return
        time.sleep(1)
        timeout -= 1
    log("Timed out waiting for PVR channels.")

def run_merge():
    notify("Starting IPTV Merge")
    xbmc.executebuiltin(f'RunPlugin({MERGE_PLUGIN_URL})')
    log("Triggered IPTV Merge plugin silently.")

def first_run_popup():
    options = [f"Every {i} Days" for i in range(1, 31)] + ["Every Kodi Startup"]
    selection = xbmcgui.Dialog().select("How often should cleanup run?", options)
    if selection == -1:
        return DEFAULT_DAYS
    if selection == 30:
        ADDON.setSetting('run_on_start', 'true')
        return -1
    else:
        ADDON.setSetting('run_on_start', 'false')
        ADDON.setSettingInt('interval_days', selection + 1)
        return selection + 1

if ADDON.getSetting('initialized') != 'true':
    result = first_run_popup()
    if result != -1:
        ADDON.setSettingInt('interval_days', result)
    ADDON.setSetting('initialized', 'true')

run_on_start = ADDON.getSettingBool('run_on_start')
interval_days = ADDON.getSettingInt('interval_days')
last_run = get_last_run()
should_run = run_on_start or (last_run is None or (datetime.datetime.now() - last_run).days >= interval_days)

if should_run:
    notify("Smart EPG Fixer running...")
    epg_cleanup()
    wait_for_pvr()
    run_merge()
    set_last_run()
    notify("EPG Fix and Merge complete.")
else:
    log("Skipping run — interval not met or not set.")

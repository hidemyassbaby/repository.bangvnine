import os
import time
import sys
import xbmc
import xbmcaddon
import xbmcvfs
from xbmcgui import Dialog

addon = xbmcaddon.Addon()
run_mode = addon.getSetting("run_mode")
ADDON_ID = "service.smart.epgfixer"

# Derived values
FOLDER = xbmcvfs.translatePath(f"special://userdata/addon_data/{ADDON_ID}")
LAST_RUN_FILE = os.path.join(FOLDER, "last_run.txt")
CHECK_INTERVAL = 6 * 60 * 60

# Simulate interval_seconds from setting
if run_mode == "every_startup":
    interval_seconds = None
else:
    try:
        interval_days = int(run_mode.replace("every_", "").replace("_days", ""))
        interval_seconds = interval_days * 86400
    except:
        interval_seconds = 7 * 86400

# --- Helpers ---
def log(msg):
    xbmc.log(f"[Smart EPG Fixer] {msg}", xbmc.LOGINFO)

def notify(title, message, duration=4000):
    xbmc.executebuiltin(f'Notification({title},{message},{duration})')

def ensure_data_folder():
    if not os.path.exists(FOLDER):
        os.makedirs(FOLDER)

def get_last_run_time():
    if not os.path.exists(LAST_RUN_FILE):
        return 0
    try:
        with open(LAST_RUN_FILE, "r") as f:
            return float(f.read().strip())
    except:
        return 0

def update_last_run_time():
    with open(LAST_RUN_FILE, "w") as f:
        f.write(str(time.time()))
    log("Updated last run time.")

# -- DEV MODE FIRST-RUN TRIGGER --
def is_first_run():
    return True  # Always true for testing

def mark_first_run_complete():
    pass  # Skip for dev version

def show_schedule_selector():
    options = ["Every startup (advanced)"] + [f"Every {i} day{'s' if i > 1 else ''}" for i in range(1, 31)]
    default_index = 6  # Every 7 days
    selection = Dialog().select("How often should Smart EPG Fixer run?", options, preselect=default_index)

    if selection == -1:
        addon.setSetting("run_mode", "every_7_days")
        notify("Smart EPG Fixer", "Default: Every 7 days", 4000)
    elif selection == 0:
        addon.setSetting("run_mode", "every_startup")
        notify("Smart EPG Fixer", "Schedule: Every startup", 4000)
    else:
        addon.setSetting("run_mode", f"every_{selection}_days")
        notify("Smart EPG Fixer", f"Schedule: Every {selection} day(s)", 4000)

# --- Cleanup ---
def delete_epg_files():
    epg_db_path = xbmcvfs.translatePath("special://userdata/Database")
    iptv_cache_path = xbmcvfs.translatePath("special://userdata/addon_data/pvr.iptvsimple")

    for fname in os.listdir(epg_db_path):
        if fname.startswith("Epg") and fname.endswith(".db"):
            try:
                os.remove(os.path.join(epg_db_path, fname))
                log(f"Deleted EPG DB: {fname}")
            except Exception as e:
                log(f"Failed to delete {fname}: {e}")

    if os.path.exists(iptv_cache_path):
        for fname in os.listdir(iptv_cache_path):
            try:
                os.remove(os.path.join(iptv_cache_path, fname))
                log(f"Deleted IPTV cache: {fname}")
            except Exception as e:
                log(f"Failed to delete {fname}: {e}")

# --- IPTV Merge ---
def run_merge():
    if xbmc.getCondVisibility("System.HasAddon(program.iptv.merge)"):
        xbmc.executebuiltin("RunPlugin(plugin://program.iptv.merge/?mode=run)")
        log("Triggered IPTV Merge")
        notify("Smart EPG Fixer", "IPTV Merge complete ✅", 4000)
    else:
        log("IPTV Merge not installed — skipping merge step.")

# --- Cleanup Task ---
def run_epg_purge():
    log("Starting EPG purge process...")
    notify("Smart EPG Fixer", "Cleaning EPG data...", 4000)

    delete_epg_files()
    time.sleep(2)
    run_merge()

    update_last_run_time()
    log("EPG purge complete.")

# --- Main Execution ---
def main():
    ensure_data_folder()

    if is_first_run():
        log("DEV MODE: Triggering setup popup every launch.")
        show_schedule_selector()
        mark_first_run_complete()

    now = time.time()
    last_run = get_last_run_time()

    if addon.getSetting("run_mode") == "every_startup":
        run_epg_purge()
    elif addon.getSetting("run_mode").startswith("every_") and interval_seconds is not None:
        if now - last_run >= interval_seconds:
            run_epg_purge()
        else:
            log("EPG cleanup not due yet.")
    else:
        log("Manual or invalid mode — skipping automatic cleanup.")

    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        if monitor.waitForAbort(CHECK_INTERVAL):
            break
        if addon.getSetting("run_mode").startswith("every_") and interval_seconds is not None:
            now = time.time()
            last_run = get_last_run_time()
            if now - last_run >= interval_seconds:
                run_epg_purge()

# --- Entry Point ---
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        run_epg_purge()
    else:
        main()

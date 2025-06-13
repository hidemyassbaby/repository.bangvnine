import os
import time
import sys
import xbmc
import xbmcaddon
import xbmcvfs
from xbmcgui import Dialog

addon = xbmcaddon.Addon()
ADDON_ID = "service.smart.epgfixer"
FOLDER = xbmcvfs.translatePath(f"special://userdata/addon_data/{ADDON_ID}")
LAST_RUN_FILE = os.path.join(FOLDER, "last_run.txt")
FIRST_RUN_FILE = os.path.join(FOLDER, "firstrun.txt")
CHECK_INTERVAL = 6 * 60 * 60

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

def is_first_run():
    return not os.path.exists(FIRST_RUN_FILE)

def mark_first_run_complete():
    with open(FIRST_RUN_FILE, "w") as f:
        f.write("done")

def show_schedule_selector():
    options = ["Every startup (advanced)"] + [f"Every {i} day{'s' if i > 1 else ''}" for i in range(1, 31)]
    default_index = 6  # 7 days
    selection = Dialog().select("How often should Smart EPG Fixer run?", options, preselect=default_index)

    if selection == -1:
        addon.setSetting("run_mode", "every_7_days")
        notify("Smart EPG Fixer", "Using default: Every 7 days", 4000)
    elif selection == 0:
        addon.setSetting("run_mode", "every_startup")
        notify("Smart EPG Fixer", "Schedule: Every startup", 4000)
    else:
        addon.setSetting("run_mode", f"every_{selection}_days")
        notify("Smart EPG Fixer", f"Schedule: Every {selection} day(s)", 4000)

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

def run_merge():
    if xbmc.getCondVisibility("System.HasAddon(program.iptv.merge)"):
        xbmc.executebuiltin("RunPlugin(plugin://program.iptv.merge/?mode=run)")
        log("Triggered IPTV Merge")
        notify("Smart EPG Fixer", "IPTV Merge complete ✅", 4000)
    else:
        log("IPTV Merge not installed — skipping merge step.")

def run_epg_purge():
    log("Starting EPG purge...")
    notify("Smart EPG Fixer", "Cleaning EPG data...", 4000)

    delete_epg_files()
    time.sleep(2)
    run_merge()

    update_last_run_time()
    log("EPG purge complete.")

def main():
    ensure_data_folder()

    if is_first_run():
        log("First install detected — showing schedule popup.")
        show_schedule_selector()
        mark_first_run_complete()

    run_mode = addon.getSetting("run_mode")

    if run_mode == "every_startup":
        log("Running EPG cleanup on startup.")
        run_epg_purge()
    else:
        try:
            days = int(run_mode.replace("every_", "").replace("_days", ""))
            interval_seconds = days * 86400
        except:
            log("Invalid or missing run_mode, defaulting to 7 days.")
            interval_seconds = 7 * 86400

        now = time.time()
        last_run = get_last_run_time()
        if now - last_run >= interval_seconds:
            log("Scheduled EPG cleanup triggered.")
            run_epg_purge()
        else:
            log("EPG cleanup not due yet.")

    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        if monitor.waitForAbort(CHECK_INTERVAL):
            break
        if run_mode.startswith("every_") and "days" in run_mode:
            try:
                days = int(run_mode.replace("every_", "").replace("_days", ""))
                if time.time() - get_last_run_time() >= days * 86400:
                    run_epg_purge()
            except:
                continue

if __name__ == "__main__":
    main()

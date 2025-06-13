import os
import time
import xbmc
import xbmcaddon
import sys

# Load settings
addon = xbmcaddon.Addon()
run_mode = addon.getSetting("run_mode")
days_interval = int(addon.getSetting("days_interval"))
interval_seconds = days_interval * 86400

LAST_RUN_FILE = xbmc.translatePath("special://userdata/addon_data/service.smart.epgfixer/last_run.txt")
CHECK_INTERVAL = 6 * 60 * 60  # Recheck every 6 hours

# --- Helpers ---
def log(msg):
    xbmc.log(f"[Smart EPG Fixer] {msg}", xbmc.LOGINFO)

def notify(title, message, duration=4000):
    xbmc.executebuiltin(f'Notification({title},{message},{duration})')

def ensure_data_folder():
    folder = os.path.dirname(LAST_RUN_FILE)
    if not os.path.exists(folder):
        os.makedirs(folder)

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

# --- Cleanup ---
def delete_epg_files():
    epg_db_path = xbmc.translatePath("special://userdata/Database")
    iptv_cache_path = xbmc.translatePath("special://userdata/addon_data/pvr.iptvsimple")

    # Delete EPG database files
    for fname in os.listdir(epg_db_path):
        if fname.startswith("Epg") and fname.endswith(".db"):
            try:
                os.remove(os.path.join(epg_db_path, fname))
                log(f"Deleted EPG DB: {fname}")
            except Exception as e:
                log(f"Failed to delete {fname}: {e}")

    # Delete IPTV Simple cache files
    if os.path.exists(iptv_cache_path):
        for fname in os.listdir(iptv_cache_path):
            try:
                os.remove(os.path.join(iptv_cache_path, fname))
                log(f"Deleted IPTV cache: {fname}")
            except Exception as e:
                log(f"Failed to delete {fname}: {e}")

# --- Merge ---
def run_merge():
    if xbmc.getCondVisibility("System.HasAddon(program.iptv.merge)"):
        xbmc.executebuiltin("RunPlugin(plugin://program.iptv.merge/?mode=run)")
        log("Triggered IPTV Merge")
        notify("Smart EPG Fixer", "IPTV Merge complete ✅", 4000)
    else:
        log("IPTV Merge not installed — skipping merge step.")

# --- Main Action ---
def run_epg_purge():
    log("Starting EPG purge process...")
    notify("Smart EPG Fixer", "Cleaning EPG data...", 4000)

    delete_epg_files()
    time.sleep(2)
    run_merge()

    update_last_run_time()
    log("EPG purge complete.")

# --- Main Entry ---
def main():
    ensure_data_folder()
    now = time.time()
    last_run = get_last_run_time()

    if run_mode == "every_startup":
        log("Running on Kodi startup.")
        run_epg_purge()
    elif run_mode == "every_x_days":
        elapsed = now - last_run
        log(f"Last run was {round(elapsed / 3600, 1)} hours ago.")
        if elapsed >= interval_seconds:
            run_epg_purge()
        else:
            log("EPG cleanup not due yet.")
    else:
        log("Manual mode — skipping automatic cleanup.")

    # Monitor to check again every few hours
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        if monitor.waitForAbort(CHECK_INTERVAL):
            break
        if run_mode == "every_x_days":
            now = time.time()
            last_run = get_last_run_time()
            if now - last_run >= interval_seconds:
                run_epg_purge()

# Allow manual run from "RunAddon"
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        run_epg_purge()
    else:
        main()

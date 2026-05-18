# Kodi 21/22 compatibility helpers for Bang Wizard
import re
import xbmc

LOGINFO = getattr(xbmc, 'LOGINFO', getattr(xbmc, 'LOGNOTICE', 1))
LOGERROR = getattr(xbmc, 'LOGERROR', 4)
LOGDEBUG = getattr(xbmc, 'LOGDEBUG', 0)

def kodi_version_number():
    label = xbmc.getInfoLabel('System.BuildVersion') or '0'
    match = re.search(r'\d+(?:\.\d+)?', label)
    try:
        return float(match.group(0)) if match else 0.0
    except Exception:
        return 0.0

def kodi_codename(version=None):
    version = kodi_version_number() if version is None else float(version)
    names = {
        16: 'Jarvis', 17: 'Krypton', 18: 'Leia', 19: 'Matrix',
        20: 'Nexus', 21: 'Omega', 22: 'Piers'
    }
    return names.get(int(version), 'Unknown')

def log(prefix, message, level=None):
    try:
        xbmc.log('[%s] %s' % (prefix, message), level if level is not None else LOGINFO)
    except Exception:
        pass

################################################################################
# Bang Wizard downloader, refreshed for Kodi 21 Omega and Kodi 22 Piers.
################################################################################

import os
import sys
import time
import zipfile
import urllib.request
import urllib.parse
import urllib.error
from http.cookiejar import CookieJar

import xbmc
import xbmcgui
import uservar
from . import wizard as wiz

ADDONTITLE = uservar.ADDONTITLE
COLOR1 = uservar.COLOR1
COLOR2 = uservar.COLOR2
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'


def download(url, dest, dp=None):
    """Download a file with Kodi 21/22 safe urllib handling and cloud-link fixes."""
    if not dp:
        dp = xbmcgui.DialogProgress()
        dp.create(ADDONTITLE, 'Preparing download')
    start_time = time.time()
    url = normalise_url(url)
    try:
        dp.update(0, '[COLOR %s]Connecting...[/COLOR]' % COLOR2)
    except Exception:
        pass
    _download_with_headers(url, dest, dp, start_time)
    _validate_download(dest)


def normalise_url(url):
    """Convert common share URLs into direct download URLs before Kodi downloads them."""
    if not url:
        return url
    try:
        url = url.replace('&amp;', '&').strip()
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()

        if 'dropbox.com' in host:
            query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
            query['dl'] = '1'
            query.pop('raw', None)
            url = urllib.parse.urlunparse((parsed.scheme or 'https', parsed.netloc, parsed.path, parsed.params, urllib.parse.urlencode(query), ''))
            url = url.replace('www.dropbox.com', 'dl.dropboxusercontent.com')

        elif 'drive.google.com' in host and '/file/d/' in parsed.path:
            file_id = parsed.path.split('/file/d/')[1].split('/')[0]
            url = 'https://drive.google.com/uc?export=download&id=%s' % file_id

        elif 'github.com' in host and '/blob/' in parsed.path:
            url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
    except Exception as exc:
        wiz.log('[Downloader] URL normalise skipped: %s' % exc, xbmc.LOGINFO)
    return url


def _download_with_headers(url, dest, dp, start_time):
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'application/zip,application/octet-stream,*/*',
        'Connection': 'close'
    }
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    request = urllib.request.Request(url, headers=headers)
    blocksize = 1024 * 64
    numblocks = 0
    try:
        with opener.open(request, timeout=120) as response:
            final_url = getattr(response, 'url', url)
            filesize = _safe_int(response.headers.get('Content-Length'))
            content_type = (response.headers.get('Content-Type') or '').lower()
            wiz.log('[Downloader] URL: %s' % url, xbmc.LOGINFO)
            wiz.log('[Downloader] Final URL: %s' % final_url, xbmc.LOGINFO)
            wiz.log('[Downloader] Content-Type: %s Size: %s' % (content_type, filesize), xbmc.LOGINFO)
            with open(dest, 'wb') as out:
                while True:
                    chunk = response.read(blocksize)
                    if not chunk:
                        break
                    out.write(chunk)
                    numblocks += 1
                    _pbhook(numblocks, blocksize, filesize, dp, start_time)
                    if _cancelled(dp):
                        raise KeyboardInterrupt('Download cancelled')
    except KeyboardInterrupt:
        _remove_partial(dest)
        try:
            dp.close()
        except Exception:
            pass
        wiz.LogNotify('[COLOR %s]%s[/COLOR]' % (COLOR1, ADDONTITLE), '[COLOR %s]Download cancelled[/COLOR]' % COLOR2)
        sys.exit()
    except Exception as exc:
        _remove_partial(dest)
        wiz.log('[Downloader] Failed: %s' % exc, xbmc.LOGERROR)
        raise


def _validate_download(dest):
    if not os.path.exists(dest) or os.path.getsize(dest) == 0:
        raise Exception('Download failed, empty file was created.')
    if _looks_like_html(dest):
        _remove_partial(dest)
        raise Exception('Downloaded page was HTML, not the build zip. Use a direct download link or Dropbox dl=1 link.')
    if dest.lower().endswith('.zip') and not zipfile.is_zipfile(dest):
        _remove_partial(dest)
        raise Exception('Downloaded file is not a valid ZIP. The host may be returning a preview page or blocked download.')


def _looks_like_html(path):
    try:
        with open(path, 'rb') as fh:
            head = fh.read(1024).lower().lstrip()
        return head.startswith(b'<!doctype html') or head.startswith(b'<html') or b'<title>dropbox' in head or b'<title>google drive' in head
    except Exception:
        return False


def _remove_partial(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _safe_int(value):
    try:
        return int(value) if value else 0
    except Exception:
        return 0


def _cancelled(dp):
    try:
        return dp.iscanceled()
    except AttributeError:
        try:
            return dp.iscanceled
        except Exception:
            return False
    except Exception:
        return False


def _pbhook(numblocks, blocksize, filesize, dp, start_time):
    try:
        downloaded = float(numblocks * blocksize)
        percent = min(int(downloaded * 100 / filesize), 100) if filesize else 0
        mb_done = downloaded / (1024 * 1024)
        mb_total = float(filesize) / (1024 * 1024) if filesize else 0
        elapsed = max(time.time() - start_time, 0.001)
        speed = downloaded / elapsed / 1024
        speed_label = 'KB/s'
        if speed >= 1024:
            speed = speed / 1024
            speed_label = 'MB/s'
        eta = int((filesize - downloaded) / max(downloaded / elapsed, 1)) if filesize and downloaded else 0
        line1 = '[COLOR %s][B]Downloaded:[/B] [COLOR %s]%.02f[/COLOR] MB' % (COLOR2, COLOR1, mb_done)
        if mb_total:
            line1 += ' of [COLOR %s]%.02f[/COLOR] MB' % (COLOR1, mb_total)
        line1 += '[/COLOR]'
        line2 = '[COLOR %s][B]Speed:[/B] [COLOR %s]%.02f[/COLOR] %s  [B]ETA:[/B] [COLOR %s]%02d:%02d[/COLOR][/COLOR]' % (COLOR2, COLOR1, speed, speed_label, COLOR1, eta // 60, eta % 60)
        dp.update(percent, line1 + '\n' + line2)
    except Exception as exc:
        wiz.log('[Downloader] Progress error: %s' % exc, xbmc.LOGINFO)

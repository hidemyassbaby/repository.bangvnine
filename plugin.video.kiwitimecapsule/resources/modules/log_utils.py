# -*- coding: utf-8 -*-

'''
 ***********************************************************
 * Chains Genocide Add-on
 *
 *
 * @file log_utils.py
 * @package plugin.video.thechains
 *
 * @copyright (c) 2025, Chains
 * @license GNU General Public License, version 3 (GPL-3.0)
 *
 ********************************************************cm*
'''

import os
from datetime import datetime
from io import open
import traceback
import xbmc
from resources.lib.modules import control


LOGDEBUG = xbmc.LOGDEBUG

addon = xbmc.Addon
name = xbmc.Addon().getAddonInfo('name')
pluginversion = xbmc.Addon().getAddonInfo("version")
kodiversion = control.getKodiVersion()
sys_platform = control.get_current_platform()


DEBUGPREFIX = f'[ {name} {pluginversion} | {kodiversion} | {sys_platform} | DEBUG | old ]'
INFOPREFIX = f'[ {name} {pluginversion}| INFO ]'
LOGPATH = control.transPath('special://logpath/')
FILENAME = 'chains_genocide.log'
LOG_FILE = os.path.join(LOGPATH, FILENAME)
debug_enabled = control.setting('debug')



def log(msg, trace=0):

    if not debug_enabled:
        return

    try:
        if not isinstance(msg, str):
            raise TypeError('Logutils.log() msg not of type str!')

        if trace == 1:
            head = DEBUGPREFIX
            failure = str(traceback.format_exc())
            _msg = f'{msg}:\n    {failure}'
        else:
            head = INFOPREFIX
            _msg = f'\n    {msg}'
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.write('\n\n\n\nstart\n')
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            line = f'[{datetime.now().date()} {str(datetime.now().time())[:8]}] {head}: {_msg}'
            f.write(line.rstrip('\r\n') + '\n\n')

    except (TypeError, IOError, OSError) as e:
        xbmc.log(f'Error in logutils.log(): {e}', xbmc.LOGERROR)

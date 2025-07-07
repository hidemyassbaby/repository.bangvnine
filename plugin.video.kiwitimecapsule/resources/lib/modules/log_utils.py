# -*- coding: utf-8 -*-
from datetime import datetime
from inspect import getframeinfo, stack
import os
import xbmc
import xbmcaddon
import xbmcvfs

Addon = xbmcaddon.Addon()
name = Addon.getAddonInfo('name').title()
pluginversion = Addon.getAddonInfo('version')


def warning(msg):
    """
    Logs a warning message, including the line number of the calling code if debug logging is enabled.

    :param msg: The message to log
    :type msg: str
    """
    msg=str(msg)

    if Addon.getSetting('show_debug')=='true':

        callerframerecord = stack()[1]
        frame = callerframerecord[0]
        info = getframeinfo(frame)

        xbmc.log('/*'+Addon.getAddonInfo('name')+'*/'+' Line: %s-> '%(str(info.lineno)+','+os.path.basename(info.filename))+msg,level=xbmc.LOGWARNING)
def error(msg):
    """
    Logs an error message, including the line number of the calling code if debug logging is enabled.

    :param msg: The message to log
    :type msg: str
    """
    msg=str(msg)
    if Addon.getSetting('show_debug')=='true':

        callerframerecord = stack()[1]
        frame = callerframerecord[0]
        info = getframeinfo(frame)
        xbmc.log('/*'+Addon.getAddonInfo('name')+'*/'+',Error, Line: %s-> '%(str(info.lineno)+','+os.path.basename(info.filename))+str(msg),level=xbmc.LOGWARNING)

def log(message, trace=False) -> None:
    '''
    Logs a message to the Kodi log file, with an optional trace flag to include the line number of
    the calling code.

    :param message: The message to log
    :type message: str
    :param trace: Include the line number of the calling code in the log message
    :type trace: bool
    '''
    debug_enabled = Addon.getSetting('show_debug') == 'true'
    if not debug_enabled:
        return

    log_path = xbmcvfs.translatePath('special://logpath')
    log_file = os.path.join(log_path, name.lower() + '.log')

    try:
        if not isinstance(message, str):
            #raise ValueError('log() message not of type str but of type ' + str(type(message)))
            message = 'warning: log() message not of type str but of type ' + str(type(message))

        prefix = f'| {name} v.{pluginversion} | DEBUG ]' if trace else '| INFO ]'
        if trace:
            caller = getframeinfo(stack()[1][0])
            message += f'\n    Called from file {caller.filename} @ {caller.lineno}'

        with open(log_file, 'a', encoding='utf8') as file:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            line = f'[{timestamp} {prefix} {message}'
            file.write(line.rstrip('\r\n') + '\n')
    except Exception as e:
        xbmc.log(f'[{name}] Logging Failure: {str(e)}', level=xbmc.LOGERROR)

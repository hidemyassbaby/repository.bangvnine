# -*- coding: utf-8 -*-

import xbmcaddon
def routing(argv1,argv2):
    from resources.main import refresh_list

    refresh_list(argv1,argv2,Addon_id=xbmcaddon.Addon())

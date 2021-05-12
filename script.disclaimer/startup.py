################################################################################
#                                                                              #
#                         Copyright (C) 2019 Barroni                           #
#                                                                              #
#  This Program is free software; you can darkredistribute it and/or modify    #
#  it under the terms of the GNU General Public License as published by        #
#  the Free Software Foundation; either version 2, or (at your option)         #
#  any later version.                                                          #
#                                                                              #
#  This Program is distributed in the hope that it will be useful,             #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of              #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the                #
#  GNU General Public License for more details.                                #
#                                                                              #
#  You should have received a copy of the GNU General Public License           #
#  along with XBMC; see the file COPYING.  If not, write to                    #
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.       #
#  http://www.gnu.org/copyleft/gpl.html                                        #
#                                                                              #
################################################################################

import os
import time
import xbmc
import xbmcgui
import xbmcaddon

addon       = xbmcaddon.Addon('script.disclaimer')
dialog 		= xbmcgui.Dialog()
accepted	= addon.getSetting('accepted')

def disclaimer():
	time.sleep(22) # time it takes for popup to show *default = 5 seconds)
	time.sleep(12) # time it takes for popup to show *default = 5 seconds)
	if dialog.yesno("[COLOR fffdd211]TERMS AND CONDITIONS[/COLOR]","","[COLOR ghostwhite]By accessing this Build, you are agreeing to be bound by these Terms and Conditions of Use and agree that you are responsible for the agreement with any applicable local laws. If you disagree with any of these terms, you are prohibited from accessing this Setup[/COLOR]","[COLOR ghostwhite]We are not affiliated with the official KODI/XBMC Foundation in any way. All the names and artworks and softwares are copyrighted by kodi.tv We are not responsible for any harm or damage caused by using Kodi / Build on your devices. By Accpting these Terms and conditions you Accept the Law and everything related to streaming We Don't Control any 3rd party Content[/COLOR]","[COLOR darkred]DECLINE[/COLOR]","[COLOR green]ACCEPT[/COLOR]"): # dialog to accept disclaimer
		# dialog.ok("[COLOR fffdd211]<<-ENTER YOUR HEADER MESSAGE HERE->>[/COLOR]", "[COLOR ghostwhite][CR]<<-ENTER YOUR MESSAGE HERE->>[/COLOR]") # dialog to add optional message to end user # delete this line if not needed
		addon.setSetting("accepted", "true") # sets the addon disclaimer setting to true
	else:
		xbmc.executebuiltin("Notification([COLOR fffdd211]SHUTTING DOWN KODI[/COLOR],[COLOR ghostwhite]You must accept the terms and conditions to use this build[/COLOR],7000,special://home/addons/script.disclaimer/resources/icon.png)") # activates notification of kodi closing # change text if needed
		time.sleep(7) # time it takes for Kodi to shutdown *default = 7 seconds)
		os._exit(1) # shuts down Kodi
			
if accepted == "false": # checks if disclaimerhas been accepted
	disclaimer() # starts the script
else:
	pass # dismisses startup of the script if disclaimer setting returns true

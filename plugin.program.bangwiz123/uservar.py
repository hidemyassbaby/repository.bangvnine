import os, xbmc, xbmcaddon
import binascii
#########################################################
### User Edit Variables #################################
#########################################################
# Enable/Disable the text file caching with 'Yes' or 'No' and age being how often it rechecks in minutes
CACHETEXT      = 'Yes'
CACHEAGE       = 30
ADDON_ID       = xbmcaddon.Addon().getAddonInfo('id')
ADDONTITLE     = 'Bang Wizard'
BUILDERNAME    = 'Bang Wizard'
#########################Make sure to change the repo to yours!!!!
EXCLUDES       = [ADDON_ID, 'roms', 'My_Builds', 'backupdir', 'script.module.kodi-six', 'script.module.six']
BUILDFILE      = 'https://raw.githubusercontent.com/hidemyassbaby/wizland/master/wizmenu.txt'
UPDATECHECK    = 0
APKFILE        = 'http://'
YOUTUBETITLE   = 'Bang' 
YOUTUBEFILE    = 'http://'
ADDONFILE      = 'http://'
ADVANCEDFILE   = 'http://'
ROMPACK        = 'http://'
EMUAPKS        = 'http://'
ADDONPACK      = 'http://'
PATH           = xbmcaddon.Addon().getAddonInfo('path')
ART            = os.path.join(PATH, 'resources', 'art')

#########################################################
### THEMING MENU ITEMS ##################################
#########################################################

##Alway test to see the color combo!!

#### NEW GUI THEME ###################################
# Choose from the following 
# Only these colors avalable
# white , blue , orange , yellow , red , purple , pink , lime , cyan, green
#Button focus color
FOCUS_BUTTON_COLOR = 'purple'
EXIT_BUTTON_COLOR = 'red'
#Highlight outline for lists
HIGHLIGHT_LIST = 'button_focus'
##No TXT file Banner
NO_TXT_FILE = 'pink'

############################################
############################################
### The full list of colors for below can found @ https://forum.kodi.tv/showthread.php?tid=210837

#Top Main buttons
MAIN_BUTTONS_TEXT = 'ghostwhite'
#All other buttons
OTHER_BUTTONS_TEXT = 'ghostwhite'
#all list text color
##FYI any color placed in the txt file will overide this
LIST_TEXT = 'yellow'


#Description text title color
DES_T_COLOR = 'ghostwhite'
#Description color
DESCOLOR = 'yellow'

#Wizard title name and verion color
WIZTITLE = 'Bang Wizard'
WIZTITLE_COLOR = 'ghostwhite'
VERTITLE_COLOR = 'ghostwhite'
VER_NUMBER_COLOR = 'yellow'
############################################################

## The colors and theme below is still used for the pop up dialogs
##Alway test to see the color combo
# You can edit these however you want, just make sure that you have a %s in each of the
# THEME's so it grabs the text from the menu item
COLOR1         = 'blue'
COLOR2         = 'yellow'
COLOR3         = 'red'
COLOR4         = 'snow'
COLOR5         = 'lime'
# Primary menu items   / %s is the menu item and is required
THEME1         = '[COLOR '+COLOR4+']%s[/COLOR]'
# Build Names          / %s is the menu item and is required
THEME2         = '[COLOR '+COLOR4+']%s[/COLOR]'
# Alternate items      / %s is the menu item and is required
THEME3         = '[COLOR '+COLOR3+']%s[/COLOR]'
# Current Build Header / %s is the menu item and is required
THEME4         = '[COLOR '+COLOR3+']Current Build:[/COLOR] [COLOR '+COLOR3+']%s[/COLOR]'
# Current Theme Header / %s is the menu item and is required
THEME5         = '[COLOR '+COLOR3+']Current Theme:[/COLOR] [COLOR '+COLOR3+']%s[/COLOR]'
THEME6         = '[COLOR '+COLOR3+'][B]%s[/B][/COLOR]'



#########################################################
# If you want to use locally stored icons the place them in the Resources/Art/
# folder of the wizard then use os.path.join(ART, 'imagename.png')
# do not place quotes around os.path.join
# Example:  ICONMAINT     = os.path.join(ART, 'mainticon.png')
#           ICONSETTINGS  = 'http://aftermathwizard.net/repo/wizard/settings.png'
# Leave as http:// for default icon
ICONBUILDS     = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONMAINT      = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONAPK        = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONADDONS     = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONYOUTUBE    = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONSAVE       = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONTRAKT      = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONREAL       = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONLOGIN      = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONCONTACT    = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
ICONSETTINGS   = 'https://i.postimg.cc/RVB6gJkQ/icon.png'
# Hide the ====== seperators 'Yes' or 'No'
HIDESPACERS    = 'No'
# Character used in seperator
SPACER         = '~'

# Message for Contact Page
# Enable 'Contact' menu item 'Yes' hide or 'No' dont hide
HIDECONTACT    = 'No'
# You can add \n to do line breaks
CONTACT        = ''
#Images used for the contact window.  http:// for default icon and fanart
CONTACTICON    = os.path.join(ART, 'icon.png')
CONTACTFANART  = 'http://'
#########################################################

#########################################################
### AUTO UPDATE #########################################
########## FOR THOSE WITH NO REPO #######################
# Enable Auto Update 'Yes' or 'No'
AUTOUPDATE     = 'No'
# Url to wizard version
WIZARDFILE     = 'http://'
#########################################################

#########################################################
### AUTO INSTALL ########################################
########## REPO IF NOT INSTALLED ########################
# Enable Auto Install 'Yes' or 'No'
AUTOINSTALL    = 'No'
# Addon ID for the repository
REPOID         = ''
# Url to Addons.xml file in your repo folder(this is so we can get the latest version)
REPOADDONXML   = 'http://'
# Url to folder zip is located in
REPOZIPURL     =  'http://'
#########################################################

#########################################################
### NOTIFICATION WINDOW##################################
#########################################################
# Enable Notification screen Yes or No
ENABLE         = 'No'
# Url to notification file
NOTIFICATION   = 'http://'
# Use either 'Text' or 'Image'
HEADERTYPE     = 'Text'
# Font size of header
FONTHEADER     = 'Font13'
HEADERMESSAGE  = 'Bang Wizard'
# url to image if using Image 424x180
HEADERIMAGE    = ''
# Font for Notification Window
FONTSETTINGS   = 'Font12'
# Background for Notification Window
BACKGROUND     = 'http://'
BACKGROUND2     = os.path.join(ART, 'ContentPanel.png')
BACKGROUND3     = os.path.join(ART, 'ContentPanel.png')
############################    #############################
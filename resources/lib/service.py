import os
import xbmc
import xbmcvfs
import xbmcgui
import xbmcaddon
import datetime
from json import loads
from threading import Thread
from PIL import ImageFilter, Image
from resources.lib.plugin import Plugin
import resources.lib.utils as utils
try:
    import urllib2 as urllib
except ImportError:
    import urllib.request as urllib
_setmain = {
    'label', 'tmdb_id', 'imdb_id'}
_setmain_artwork = {
    'icon', 'poster', 'thumb', 'fanart', 'discart', 'clearart', 'clearlogo', 'landscape', 'banner'}
_setinfo = {
    'title', 'originaltitle', 'tvshowtitle', 'plot', 'rating', 'votes', 'premiered', 'year', 'imdbnumber', 'tagline',
    'status', 'episode', 'season', 'genre', 'set', 'studio', 'country', 'MPAA', 'director', 'writer', 'trailer', 'top250'}
_setprop = {
    'tvdb_id', 'tvshow.tvdb_id', 'tvshow.tmdb_id', 'tvshow.imdb_id', 'biography', 'birthday', 'age', 'deathday',
    'character', 'department', 'job', 'known_for', 'role', 'born', 'creator', 'aliases', 'budget', 'revenue',
    'set.tmdb_id', 'set.name', 'set.poster', 'set.fanart'}
_setprop_ratings = {
    'awards', 'metacritic_rating', 'imdb_rating', 'imdb_votes', 'rottentomatoes_rating', 'rottentomatoes_image',
    'rottentomatoes_reviewtotal', 'rottentomatoes_reviewsfresh', 'rottentomatoes_reviewsrotten',
    'rottentomatoes_consensus', 'rottentomatoes_usermeter', 'rottentomatoes_userreviews', 'trakt_rating', 'trakt_votes',
    'oscar_wins', 'oscar_nominations', 'award_wins', 'award_nominations', 'tmdb_rating', 'tmdb_votes'}
_homewindow = xbmcgui.Window(10000)


class CronJob(Thread):
    def __init__(self, update_hour=0):
        Thread.__init__(self)
        self.kodimonitor = xbmc.Monitor()
        self.exit = False
        self.poll_time = 1800  # Poll every 30 mins since we don't need to get exact time for update
        self.addon = xbmcaddon.Addon('plugin.video.themoviedb.helper')
        self.update_hour = update_hour

    def run(self):
        self.kodimonitor.waitForAbort(450)  # Delay start-up to give time for datetime python module
        self.nexttime = datetime.datetime.combine(datetime.datetime.today(), datetime.time(utils.try_parse_int(self.update_hour)))  # Get today at hour
        self.lasttime = xbmc.getInfoLabel('Skin.String(TMDbHelper.AutoUpdate.LastTime)')  # Get last update
        self.lasttime = utils.convert_timestamp(self.lasttime) if self.lasttime else None
        if self.lasttime and self.lasttime > self.nexttime:
            self.nexttime += datetime.timedelta(hours=24)  # Already updated today so set for tomorrow

        while not self.kodimonitor.abortRequested() and not self.exit and self.poll_time:
            if self.addon.getSettingBool('library_autoupdate'):
                if datetime.datetime.now() > self.nexttime:  # Scheduled time has past so lets update
                    xbmc.executebuiltin('RunScript(plugin.video.themoviedb.helper,library_autoupdate)')
                    xbmc.executebuiltin('Skin.SetString(TMDbHelper.AutoUpdate.LastTime,{})'.format(datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")))
                    self.nexttime += datetime.timedelta(hours=24)  # Set next update for tomorrow
            self.kodimonitor.waitForAbort(self.poll_time)


class BlurImage(Thread):
    def __init__(self, artwork=None):
        Thread.__init__(self)
        self.radius = 20
        self.addon_path = utils.makepath('special://profile/addon_data/plugin.video.themoviedb.helper/blur/')
        self.image = artwork

    def run(self):
        if not self.image:
            _homewindow.clearProperty('TMDbHelper.ListItem.BlurImage')
            return
        filename = '{}{}.png'.format(utils.md5hash(self.image), self.radius)
        blurname = self.blur(self.image, filename)
        _homewindow.setProperty('TMDbHelper.ListItem.BlurImage', blurname)

    def blur(self, source, filename):
        destination = self.addon_path + filename
        try:
            if xbmcvfs.exists(destination):
                os.utime(destination, None)
            else:
                img = self.openimage(source, self.addon_path, filename)
                img.thumbnail((256, 256))
                img = img.convert('RGB')
                img = img.filter(ImageFilter.GaussianBlur(self.radius))
                img.save(destination)
                img.close()

            return destination

        except Exception:
            return ''

    def openimage(self, image, targetpath, filename):
        """ Open image helper with thanks to sualfred """
        # some paths require unquoting to get a valid cached thumb hash
        cached_image_path = urllib.unquote(image.replace('image://', ''))
        if cached_image_path.endswith('/'):
            cached_image_path = cached_image_path[:-1]

        cached_files = []
        for path in [xbmc.getCacheThumbName(cached_image_path), xbmc.getCacheThumbName(image)]:
            cached_files.append(os.path.join('special://profile/Thumbnails/', path[0], path[:-4] + '.jpg'))
            cached_files.append(os.path.join('special://profile/Thumbnails/', path[0], path[:-4] + '.png'))
            cached_files.append(os.path.join('special://profile/Thumbnails/Video/', path[0], path))

        for i in range(1, 4):
            try:
                ''' Try to get cached image at first
                '''
                for cache in cached_files:
                    if xbmcvfs.exists(cache):
                        try:
                            img = Image.open(xbmc.translatePath(cache))
                            return img

                        except Exception as error:
                            utils.kodi_log('Image error: Could not open cached image --> %s' % error, 2)

                ''' Skin images will be tried to be accessed directly. For all other ones
                    the source will be copied to the addon_data folder to get access.
                '''
                if xbmc.skinHasImage(image):
                    if not image.startswith('special://skin'):
                        image = os.path.join('special://skin/media/', image)

                    try:  # in case image is packed in textures.xbt
                        img = Image.open(xbmc.translatePath(image))
                        return img

                    except Exception:
                        return ''

                else:
                    targetfile = os.path.join(targetpath, filename)
                    if not xbmcvfs.exists(targetfile):
                        xbmcvfs.copy(image, targetfile)

                    img = Image.open(targetfile)
                    return img

            except Exception as error:
                utils.kodi_log('Image error: Could not get image for %s (try %d) -> %s' % (image, i, error), 2)
                xbmc.sleep(500)
                pass

        return ''


class CommonMonitorFunctions(Plugin):
    def __init__(self):
        super(CommonMonitorFunctions, self).__init__()
        self.property_basename = 'TMDbHelper'

    def set_property(self, key, value):
        try:
            if value is None:
                _homewindow.clearProperty('{}.{}'.format(self.property_basename, key))
            else:
                _homewindow.setProperty('{}.{}'.format(self.property_basename, key), u'{0}'.format(value))
        except Exception as exc:
            utils.kodi_log(u'{0}{1}'.format(key, exc), 1)

    def set_iter_properties(self, dictionary, keys):
        if not isinstance(dictionary, dict):
            return
        for k in keys:
            try:
                v = dictionary.get(k, '')
                if isinstance(v, list):
                    try:
                        v = ' / '.join(v)
                    except Exception as exc:
                        utils.kodi_log(u'Func: set_iter_properties - list\n{0}'.format(exc), 1)
                self.properties.add(k)
                self.set_property(k, v)
            except Exception as exc:
                'k: {0} e: {1}'.format(k, exc)

    def set_indx_properties(self, dictionary):
        if not isinstance(dictionary, dict):
            return

        indxprops = set()
        for k, v in dictionary.items():
            if k in self.properties or k in _setprop_ratings or k in _setmain_artwork:
                continue
            try:
                v = v or ''
                self.set_property(k, v)
                indxprops.add(k)
            except Exception as exc:
                utils.kodi_log(u'k: {0} v: {1} e: {2}'.format(k, v, exc), 1)

        for k in (self.indxproperties - indxprops):
            self.clear_property(k)
        self.indxproperties = indxprops.copy()

    def set_list_properties(self, items, key, prop):
        if not isinstance(items, list):
            return
        try:
            joinlist = [i.get(key) for i in items[:10] if i.get(key)]
            joinlist = ' / '.join(joinlist)
            self.properties.add(prop)
            self.set_property(prop, joinlist)
        except Exception as exc:
            utils.kodi_log(u'Func: set_list_properties\n{0}'.format(exc), 1)

    def set_time_properties(self, duration):
        try:
            minutes = duration // 60 % 60
            hours = duration // 60 // 60
            totalmin = duration // 60
            self.set_property('Duration', totalmin)
            self.set_property('Duration_H', hours)
            self.set_property('Duration_M', minutes)
            self.set_property('Duration_HHMM', '{0:02d}:{1:02d}'.format(hours, minutes))
            self.properties.update(['Duration', 'Duration_H', 'Duration_M', 'Duration_HHMM'])
        except Exception as exc:
            'Func: set_time_properties\n{0}'.format(exc)

    def set_properties(self, item):
        self.set_iter_properties(item, _setmain)
        self.set_iter_properties(item.get('infolabels', {}), _setinfo)
        self.set_iter_properties(item.get('infoproperties', {}), _setprop)
        self.set_time_properties(item.get('infolabels', {}).get('duration', 0))
        self.set_list_properties(item.get('cast', []), 'name', 'cast')
        if xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.DisableExtendedProperties)"):
            self.set_indx_properties(item.get('infoproperties', {}))
        _homewindow.clearProperty('TMDbHelper.IsUpdating')

    def get_tmdb_id(self, itemtype, imdb_id=None, query=None, year=None):
        try:
            if imdb_id and imdb_id.startswith('tt'):
                return self.tmdb.get_tmdb_id(itemtype=itemtype, imdb_id=imdb_id)
            return self.tmdb.get_tmdb_id(itemtype=itemtype, query=query, year=year)
        except Exception as exc:
            utils.kodi_log(u'Func: get_tmdb_id\n{0}'.format(exc), 1)
            return

    def clear_properties(self, ignorekeys=None):
        ignorekeys = ignorekeys or set()
        for k in self.properties - ignorekeys:
            self.clear_property(k)
        self.properties = set()
        for k in self.indxproperties:
            self.clear_property(k)
        self.indxproperties = set()
        self.pre_item = None

    def clear_property_list(self, properties):
        for k in properties:
            self.clear_property(k)

    def clear_property(self, key):
        try:
            _homewindow.clearProperty('{}.{}'.format(self.property_basename, key))
        except Exception as exc:
            utils.kodi_log(u'Func: clear_property\n{0}{1}'.format(key, exc), 1)


class PlayerMonitor(xbmc.Player, CommonMonitorFunctions):
    def __init__(self):
        xbmc.Player.__init__(self)
        CommonMonitorFunctions.__init__(self)
        self.property_basename = 'TMDbHelper.Player'
        self.properties = set()
        self.indxproperties = set()
        self.playerstring = None
        self.exit = False
        self.reset_properties()

    def onAVStarted(self):
        self.reset_properties()
        self.get_playingitem()

    def onPlayBackEnded(self):
        self.set_dbidwatched()
        self.reset_properties()

    def onPlayBackStopped(self):
        self.set_dbidwatched()
        self.reset_properties()

    def set_dbidwatched_rpc(self, dbid=None, dbtype=None):
        if not dbid or not dbtype:
            return
        method = "VideoLibrary.Get{}Details".format(dbtype.capitalize())
        params = {"{}id".format(dbtype): dbid, "properties": ["playcount"]}
        json_info = utils.get_jsonrpc(method=method, params=params)
        playcount = json_info.get('result', {}).get('{}details'.format(dbtype), {}).get('playcount', 0)
        playcount = utils.try_parse_int(playcount) + 1
        method = "VideoLibrary.Set{}Details".format(dbtype.capitalize())
        params = {"{}id".format(dbtype): dbid, "playcount": playcount}
        return utils.get_jsonrpc(method=method, params=params)

    def set_dbidwatched(self):
        if not self.playerstring or not self.playerstring.get('tmdb_id'):
            return
        if not self.currenttime or not self.totaltime:
            return  # No time set so skip
        if '{}'.format(self.playerstring.get('tmdb_id')) != '{}'.format(self.details.get('tmdb_id')):
            return  # Item in the player doesn't match so don't mark as watched
        dbid = self.get_db_info(info='dbid', **self.playerstring)
        if not dbid:
            return
        progress = ((self.currenttime / self.totaltime) * 100)
        if progress < 75:
            return  # Only update if progress is 75% or more
        if self.playerstring.get('tmdbtype') == 'episode':
            self.set_dbidwatched_rpc(dbid=dbid, dbtype='episode')
        elif self.playerstring.get('tmdbtype') == 'movie':
            self.set_dbidwatched_rpc(dbid=dbid, dbtype='movie')

    def get_playingitem(self):
        if not self.isPlayingVideo():
            return  # Not a video so don't get info
        if self.getVideoInfoTag().getMediaType() not in ['movie', 'episode']:
            return  # Not a movie or episode so don't get info TODO Maybe get PVR details also?
        self.playerstring = _homewindow.getProperty('TMDbHelper.PlayerInfoString')
        self.playerstring = loads(self.playerstring) if self.playerstring else None

        self.totaltime = self.getTotalTime()
        self.dbtype = self.getVideoInfoTag().getMediaType()
        self.dbid = self.getVideoInfoTag().getDbId()
        self.imdb_id = self.getVideoInfoTag().getIMDBNumber()
        self.query = self.getVideoInfoTag().getTVShowTitle() if self.dbtype == 'episode' else self.getVideoInfoTag().getTitle()
        self.year = self.getVideoInfoTag().getYear() if self.dbtype == 'movie' else None
        self.season = self.getVideoInfoTag().getSeason() if self.dbtype == 'episodes' else None
        self.episode = self.getVideoInfoTag().getEpisode() if self.dbtype == 'episodes' else None
        self.query = utils.try_decode_string(self.query)

        self.tmdbtype = 'movie' if self.dbtype == 'movie' else 'tv'
        self.tmdb_id = self.get_tmdb_id(self.tmdbtype, self.imdb_id, self.query, self.year)
        self.details = self.tmdb.get_detailed_item(self.tmdbtype, self.tmdb_id, season=self.season, episode=self.episode)

        if not self.details:
            return self.reset_properties()  # No self.details so lets clear everything

        if xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.DisableRatings)"):
            self.details = self.get_omdb_ratings(self.details) if self.tmdbtype == 'movie' else self.details
            self.details = self.get_top250_rank(self.details) if self.tmdbtype == 'movie' else self.details
            self.details = self.get_trakt_ratings(self.details, self.tmdbtype, self.tmdb_id, self.season, self.episode) if self.tmdbtype in ['movie', 'tv'] else self.details
            self.set_iter_properties(self.details.get('infoproperties', {}), _setprop_ratings)

        if xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.DisableArtwork)"):
            self.details = self.get_fanarttv_artwork(self.details, self.tmdbtype) if self.addon.getSettingBool('service_fanarttv_lookup') else self.details
            self.details = self.get_kodi_artwork(self.details, self.dbtype, self.dbid) if self.addon.getSettingBool('local_db') else self.details
            self.set_iter_properties(self.details, _setmain_artwork)

        self.set_properties(self.details)

    def reset_properties(self):
        self.clear_properties()
        self.properties = set()
        self.indxproperties = set()
        self.totaltime = 0
        self.currenttime = 0
        self.dbtype = None
        self.imdb_id = None
        self.query = None
        self.year = None
        self.season = None
        self.episode = None
        self.dbid = None
        self.tmdb_id = None
        self.details = {}
        self.tmdbtype = None


class ServiceMonitor(CommonMonitorFunctions):
    def __init__(self):
        super(ServiceMonitor, self).__init__()
        self.property_basename = 'TMDbHelper.ListItem'
        self.kodimonitor = xbmc.Monitor()
        self.container = 'Container.'
        self.containeritem = 'ListItem.'
        self.exit = False
        self.cur_item = 0
        self.pre_item = 1
        self.pre_folder = None
        self.cur_folder = None
        self.properties = set()
        self.indxproperties = set()
        self.cron_job = CronJob(self.addon.getSettingInt('library_autoupdate_hour'))
        self.cron_job.setName('Cron Thread')
        self.playermonitor = None
        self.run_monitor()

    def run_monitor(self):
        _homewindow.setProperty('TMDbHelper.ServiceStarted', 'True')

        if self.addon.getSettingString('trakt_token'):
            _homewindow.setProperty('TMDbHelper.TraktIsAuth', 'True')
            self.get_trakt_usernameslug()

        self.cron_job.start()

        while not self.kodimonitor.abortRequested() and not self.exit:
            if _homewindow.getProperty('TMDbHelper.ServiceStop'):
                self.cron_job.exit = True
                self.exit = True

            # Startup our playmonitor if we haven't already
            elif not self.playermonitor:
                self.playermonitor = PlayerMonitor()
                self.kodimonitor.waitForAbort(1)

            # If we're in fullscreen video then we should update the playermonitor time
            elif xbmc.getCondVisibility("Window.IsVisible(fullscreenvideo)") and self.playermonitor.isPlayingVideo():
                self.playermonitor.currenttime = self.playermonitor.getTime()
                self.kodimonitor.waitForAbort(1)

            # Sit idle in a holding pattern if the skin doesn't need the service monitor yet
            elif xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.Service) | System.ScreenSaverActive"):
                self.kodimonitor.waitForAbort(30)

            # skip when modal dialogs are opened (e.g. textviewer in musicinfo dialog)
            elif xbmc.getCondVisibility(
                    "Window.IsActive(DialogSelect.xml) | Window.IsActive(progressdialog) | "
                    "Window.IsActive(contextmenu) | Window.IsActive(busydialog) | Window.IsActive(shutdownmenu)"):
                self.kodimonitor.waitForAbort(2)

            # skip when container scrolling
            elif xbmc.getCondVisibility(
                    "Container.OnScrollNext | Container.OnScrollPrevious | Container.Scrolling"):
                if (self.properties or self.indxproperties) and self.get_cur_item() != self.pre_item:
                    ignorekeys = _setmain_artwork if self.dbtype in ['episodes', 'seasons'] else None
                    self.clear_properties(ignorekeys=ignorekeys)
                self.kodimonitor.waitForAbort(1)

            # media window is opened or widgetcontainer set - start listitem monitoring!
            elif xbmc.getCondVisibility(
                    "Window.IsMedia | Window.IsVisible(MyPVRChannels.xml) | Window.IsVisible(MyPVRGuide.xml) | Window.IsVisible(DialogPVRInfo.xml) | "
                    "!String.IsEmpty(Window(Home).Property(TMDbHelper.WidgetContainer)) | Window.IsVisible(movieinformation)"):
                self.get_listitem()
                self.kodimonitor.waitForAbort(0.3)

            # clear window props
            elif self.properties or self.indxproperties:
                self.clear_properties()

            # Otherwise just sit here and wait
            else:
                self.kodimonitor.waitForAbort(1)

        # Some clean-up once service exits
        self.exit_monitor()

    def exit_monitor(self):
        self.playermonitor.exit = True
        del self.playermonitor
        self.clear_properties()
        _homewindow.clearProperty('TMDbHelper.ServiceStarted')
        _homewindow.clearProperty('TMDbHelper.ServiceStop')

    def get_cur_item(self):
        self.dbtype = self.get_dbtype()
        self.dbid = self.get_infolabel('DBID')
        self.imdb_id = self.get_infolabel('IMDBNumber')
        self.query = self.get_infolabel('TvShowTitle') or self.get_infolabel('Title') or self.get_infolabel('Label')
        self.year = self.get_infolabel('year')
        self.season = self.get_infolabel('Season') if self.dbtype == 'episodes' else ''
        self.episode = self.get_infolabel('Episode') if self.dbtype == 'episodes' else ''
        self.query = utils.try_decode_string(self.query)
        return u'{0}.{1}.{2}.{3}.{4}'.format(self.imdb_id, self.query, self.year, self.season, self.episode)

    def is_same_item(self, update=True, pre_item=None):
        pre_item = pre_item or self.pre_item
        self.cur_item = self.get_cur_item()
        if self.cur_item == pre_item:
            return self.cur_item
        if update:
            self.pre_item = self.cur_item

    def get_artwork(self, source=''):
        source = source or _homewindow.getProperty('TMDbHelper.Blur.SourceImage')
        source = source.lower()
        infolabels = ['Art(thumb)']
        if source == 'poster':
            infolabels = ['Art(tvshow.poster)', 'Art(poster)', 'Art(thumb)']
        elif source == 'fanart':
            infolabels = ['Art(fanart)', 'Art(thumb)']
        elif source == 'landscape':
            infolabels = ['Art(landscape)', 'Art(fanart)', 'Art(thumb)']
        elif source and source != 'thumb':
            infolabels = source.split("|")
        fallback = _homewindow.getProperty('TMDbHelper.Blur.Fallback')
        for i in infolabels:
            artwork = self.get_infolabel(i)
            if artwork:
                return artwork
        return fallback

    def get_listitem(self):
        try:
            self.get_container()
            if self.is_same_item():
                return  # Current item was the previous item so no need to do a look-up

            self.cur_folder = '{0}{1}{2}'.format(
                self.container, self.get_dbtype(),
                xbmc.getInfoLabel('{0}NumItems'.format(self.container)))
            if self.cur_folder != self.pre_folder:
                self.clear_properties()  # Clear props if the folder changed
                self.pre_folder = self.cur_folder
            if self.get_infolabel('Label') == '..':
                self.clear_properties()
                return  # Parent folder so clear properties and don't do look-up

            # Blur Image
            if xbmc.getCondVisibility("Skin.HasSetting(TMDbHelper.EnableBlur)"):
                self.blur_img = BlurImage(artwork=self.get_artwork())
                self.blur_img.setName('blur_img')
                self.blur_img.start()

            if self.dbtype in ['tvshows', 'seasons', 'episodes']:
                tmdbtype = 'tv'
            elif self.dbtype in ['movies']:
                tmdbtype = 'movie'
            elif self.dbtype in ['sets']:
                tmdbtype = 'collection'
            elif self.dbtype in ['actors', 'directors']:
                tmdbtype = 'person'
            else:
                return

            _homewindow.setProperty('TMDbHelper.IsUpdating', 'True')

            if self.dbtype not in ['episodes', 'seasons']:
                self.clear_property_list(_setmain_artwork)
            self.clear_property_list(_setprop_ratings)

            tmdb_id = self.get_tmdb_id(tmdbtype, self.imdb_id, self.query, self.year if tmdbtype == 'movie' else None)
            details = self.tmdb.get_detailed_item(tmdbtype, tmdb_id, season=self.season, episode=self.episode)

            if not details:
                self.clear_properties()  # No details so lets clear everything
                return

            if xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.DisableArtwork)"):
                thread_artwork = Thread(target=self.process_artwork, args=[details, tmdbtype])
                thread_artwork.start()

            if not self.is_same_item():
                ignorekeys = _setmain_artwork if self.dbtype in ['episodes', 'seasons'] else None
                self.clear_properties(ignorekeys=ignorekeys)  # Item changed so clear everything
                return

            if xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.DisablePersonStats)"):
                details = self.get_kodi_person_stats(details) if tmdbtype == 'person' else details

            if xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.DisableRatings)"):
                thread_ratings = Thread(target=self.process_ratings, args=[details, tmdbtype, tmdb_id])
                thread_ratings.start()

            self.set_properties(details)

        except Exception as exc:
            utils.kodi_log(u'Func: get_listitem\n{0}'.format(exc), 1)

    def process_ratings(self, details, tmdbtype, tmdb_id):
        try:
            if tmdbtype not in ['movie', 'tv']:
                return
            pre_item = self.pre_item
            details = self.get_omdb_ratings(details) if tmdbtype == 'movie' else details
            details = self.get_top250_rank(details) if tmdbtype == 'movie' else details
            details = self.get_trakt_ratings(details, tmdbtype, tmdb_id, self.season, self.episode) if tmdbtype in ['movie', 'tv'] else details
            if not self.is_same_item(update=False, pre_item=pre_item):
                return
            self.set_iter_properties(details.get('infoproperties', {}), _setprop_ratings)
        except Exception as exc:
            utils.kodi_log(u'Func: process_ratings\n{}'.format(exc), 1)

    def process_artwork(self, details, tmdbtype):
        try:
            if self.dbtype not in ['movies', 'tvshows', 'episodes'] and tmdbtype not in ['movie', 'tv']:
                return
            pre_item = self.pre_item
            details = self.get_fanarttv_artwork(details, tmdbtype) if self.addon.getSettingBool('service_fanarttv_lookup') else details
            details = self.get_kodi_artwork(details, self.dbtype, self.dbid) if self.addon.getSettingBool('local_db') else details
            if not self.is_same_item(update=False, pre_item=pre_item):
                return
            self.set_iter_properties(details, _setmain_artwork)
        except Exception as exc:
            utils.kodi_log(u'Func: process_ratings\n{}'.format(exc), 1)

    def get_container(self):
        widgetid = utils.try_parse_int(_homewindow.getProperty('TMDbHelper.WidgetContainer'))
        self.container = 'Container({0}).'.format(widgetid) if widgetid else 'Container.'
        self.containeritem = '{0}ListItem.'.format(self.container)
        if xbmc.getCondVisibility("Window.IsVisible(DialogPVRInfo.xml) | Window.IsVisible(movieinformation)"):
            if xbmc.getCondVisibility("!Skin.HasSetting(TMDbHelper.ForceWidgetContainer)"):
                self.containeritem = 'ListItem.'  # In info dialog just use listitem unless force widget container set

    def get_dbtype(self):
        dbtype = xbmc.getInfoLabel('{0}DBTYPE'.format(self.containeritem))
        dbtype = 'actor' if dbtype == 'video' and xbmc.getInfoLabel('{0}Property(Container.Type)'.format(self.containeritem)) == 'person' else dbtype
        if xbmc.getCondVisibility("Window.IsVisible(DialogPVRInfo.xml) | Window.IsVisible(MyPVRChannels.xml) | Window.IsVisible(MyPVRGuide.xml)"):
            dbtype = 'tvshow'
        return '{0}s'.format(dbtype) if dbtype else xbmc.getInfoLabel('Container.Content()') or ''

    def get_infolabel(self, infolabel):
        return xbmc.getInfoLabel('{0}{1}'.format(self.containeritem, infolabel))

    def get_position(self):
        return xbmc.getInfoLabel('{0}CurrentItem'.format(self.container))

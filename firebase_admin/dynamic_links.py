# Copyright 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Firebase Dynamic Links module.

This module lets admins get statistics for a Firebase dynamic link.
"""

from six.moves import urllib
import six

from firebase_admin import _http_client
from firebase_admin import _utils


_LINKS_ATTRIBUTE = '_dynamic_links'
_LINKS_BASE_URL = 'https://firebasedynamiclinks.googleapis.com/v1/'

PLATFORM_DESKTOP = 'desktop'
PLATFORM_IOS = 'ios'
PLATFORM_ANDROID = 'android'

EVENT_TYPE_CLICK = 'click'
EVENT_TYPE_REDIRECT = 'redirect'
EVENT_TYPE_APP_INSTALL = 'app_install'
EVENT_TYPE_APP_FIRST_OPEN = 'app_first_open'
EVENT_TYPE_APP_RE_OPEN = 'app_re_open'

def get_link_stats(short_link, stat_options, app=None):
    """ Returns a `LinkStats` object with the event statistics for the given short link

    Args:
        short_link: The string of the designated short link. e.g. https://abc12.app.goo.gl/link
                    The link must belong to the project associated with the service account
                    used to call this API.
        stat_options: An object containing a single field "duration_days" for which the statistics
                      are retrieved.
        app: (optional) `firebase_app` instance. (If missing uses default app.)

    Returns:
        LinkStats: An `LinkStats` object. (containing an array of `EventStats`)

    Raises:
        ValueError: If any of the arguments are invalid.
                    url must start with the protocol "http"
                    stat_options should have a field with duration_days > 0
    """
    return _get_link_service(app)._get_stats(short_link, stat_options)

def _get_link_service(app):
    """Returns an _LinksService instance for an App.

    If the App already has a _LinksService associated with it, simply returns
    it. Otherwise creates a new _LinksService, and adds it to the App before
    returning it.

    Args:
        app: A Firebase App instance (or None to use the default App).

    Returns:
        _LinksService: An `_LinksService` for the specified App instance.

    Raises:
        ValueError: If the app argument is invalid.
    """
    return _utils.get_app_service(app, _LINKS_ATTRIBUTE, _LinksService)


class LinkStats(object):
    """The `LinkStats` object is returned by get_link_stats, it contains a list of `EventStats`"""
    def __init__(self, event_stats):
        if not isinstance(event_stats, (list, tuple)):
            raise ValueError('Invalid data argument: {0}. Must be a list or tuple'
                             .format(event_stats))
        if event_stats and not isinstance(event_stats[0], EventStats):
            raise ValueError('Invalid data argument: elements of event stats must be' +
                             ' "EventStats", found{}'.format(type(event_stats[0])))
        self._stats = event_stats

    @property
    def event_stats(self):
        """Returns the event statistics for this link, for the requested period.

        Returns:
          event_stats: A list of `EventStats`.
        """
        return self._stats

class EventStats(object):
    """`EventStats` is a single stat item containing (platform, event, count)"""

    _platforms = {
        'DESKTOP': PLATFORM_DESKTOP,
        'IOS': PLATFORM_IOS,
        'ANDROID': PLATFORM_ANDROID
    }

    _event_types = {
        'CLICK': EVENT_TYPE_CLICK,
        'REDIRECT': EVENT_TYPE_REDIRECT,
        'APP_INSTALL': EVENT_TYPE_APP_INSTALL,
        'APP_FIRST_OPEN': EVENT_TYPE_APP_FIRST_OPEN,
        'APP_RE_OPEN': EVENT_TYPE_APP_RE_OPEN
    }

    def __init__(self, platform, event, count):
        """Create new instance of EventStats(platform, event, count)"""
        self.platform = platform
        self.event = event
        self.count = count

    def __repr__(self):
        return"EventStats(platform: '{}', event: '{}', count: '{}')".format(
            self.platform, self.event, self.count)

    @classmethod
    def make_event_stat(cls, platform, event, count):
        """make_event_stat creates an EventStat object given the appropriate constants. e.g:
        make_event_stat(platform=PLATFORM_DESKTOP, event=EVENT_TYPE_REDIRECT, count=4)"""
        return EventStats(cls._platforms[platform],
                          cls._event_types[event],
                          int(count))

    @property
    def platform(self):
        return self._platform

    @platform.setter
    def platform(self, platform):
        if isinstance(platform, six.string_types) and platform in self._platforms.keys():
            raise ValueError(('Raw string {} detected. Use one of the dynamic_links.PLATFORM_...' +
                              ' constants, or the make_event_stat() method.').format(platform))
        if not isinstance(platform, six.string_types) or platform not in self._platforms.values():
            raise ValueError('platform {}, not recognized'.format(platform))
        self._platform = platform

    @property
    def event(self):
        return self._event

    @event.setter
    def event(self, event):
        if isinstance(event, six.string_types) and event in self._event_types.keys():
            raise ValueError(('Raw string {} detected. Use one of the dynamic_links.EVENT_TYPES_' +
                              ' constants, or the make_event_stat() method.').format(event))
        if not isinstance(event, six.string_types) or event not in self._event_types.values():
            raise ValueError('event_type {}, not recognized'.format(event))
        self._event = event

    @property
    def count(self):
        return self._count

    @count.setter
    def count(self, count):
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError('Count: {} must be a non negative int'.format(count))
        self._count = count


class StatOptions(object):
    def __init__(self, duration_days):
        self.duration_days = duration_days

    @property
    def duration_days(self):
        return self._duration_days

    @duration_days.setter
    def duration_days(self, duration_days):
        if (isinstance(duration_days, bool)
                or not isinstance(duration_days, int)
                or duration_days < 1):
            raise ValueError('duration_days must be positive integer (got {})'
                             .format(duration_days))
        self._duration_days = duration_days

class _LinksService(object):
    """Provides methods for the Firebase dynamic links interaction"""
    def __init__(self, app):
        self._client = _http_client.JsonHttpClient(
            credential=app.credential.get_credential(),
            base_url=_LINKS_BASE_URL)
        self._timeout = app.options.get('httpTimeout')
        self._request_string = '{0}/linkStats?durationDays={1}'

    def _format_request_string(self, short_link, options):
        days = options.duration_days
        # Complaints about the named second argument needed to replace "/"
        #pylint: disable=redundant-keyword-arg
        url_quoted = urllib.parse.quote(short_link, safe='')
        #pylint: enable=redundant-keyword-arg
        return self._request_string.format(url_quoted, days)

    def _get_stats(self, short_link, stat_options):
        if(not isinstance(short_link, six.string_types)
           or not short_link.startswith('https://')):
            raise ValueError('short_link must be a string and begin with "https://".')
        if not isinstance(stat_options, StatOptions):
            raise ValueError('stat_options must be of type StatOptions.')

        request_string = self._format_request_string(short_link, stat_options)
        resp = self._client.body('get', request_string)
        link_event_stats_dict = resp.get('linkEventStats', [])
        event_stats = [EventStats.make_event_stat(**es) for es in link_event_stats_dict]
        return LinkStats(event_stats)

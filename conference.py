#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""


from datetime import datetime
from datetime import time

import json

import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb
from google.appengine.ext import db
from google.net.proto.ProtocolBuffer import ProtocolBufferDecodeError

from models import ConflictException
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import StringMessage
from models import BooleanMessage
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms
from models import TeeShirtSize
from models import Speaker
from models import SpeakerForm
from models import SpeakerForms
from models import Session
from models import SessionForm
from models import SessionForms
from models import QueryForm
from models import QueryForms

from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE

from utils import getUserId

__author__ = 'wesc+api@google.com (Wesley Chun)'

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
MEMCACHE_FEATURED_SPEAKER_KEY = "FEATURED_SPEAKER"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"]
}

OPERATORS = {
    'EQ': '=',
    'GT': '>',
    'GTEQ': '>=',
    'LT': '<',
    'LTEQ': '<=',
    'NE': '!='
}

FIELDS = {
    'CITY': 'city',
    'TOPIC': 'topics',
    'MONTH': 'month',
    'MAX_ATTENDEES': 'maxAttendees'
}

SESSION_FIELDS = {
    'NAME': 'name',
    'SPEAKER': 'websafeSpeakerKey',
    'DURATION': 'duration',
    'TYPE_OF_SESSION': 'typeOfSession',
    # 'DATE': 'date',
    # 'START_TIME': 'startTime'
}
CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

SESSION_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1, required=True),
    typeOfSession=messages.StringField(2)
)

SESSION_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1, required=True)
)

WISHLIST_POST_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    sessionKey=messages.StringField(1, required=True)
)

SPEAKER_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeSpeakerKey=messages.StringField(1, required=True),
)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(
    name='conference',
    version='v1',
    audiences=[ANDROID_AUDIENCE],
    allowed_client_ids=[
        WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID, ANDROID_CLIENT_ID, IOS_CLIENT_ID
    ],
    scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException(
                "Conference 'name' field required"
            )

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {
            field.name:
                getattr(request, field.name) for field in request.all_fields()
        }
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Msg)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on startd
        if data['startDate']:
            data['startDate'] = datetime.strptime(
                data['startDate'][:10], "%Y-%m-%d"
            ).date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(
                data['endDate'][:10], "%Y-%m-%d"
            ).date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(
            params={'email': user.email(), 'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )
        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {
            field.name:
                getattr(request, field.name) for field in request.all_fields()
        }

        # update existing conference
        try:
            conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'websafeConferenceKey seems to be invalid')
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = self._getProfileFromUser()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(
        ConferenceForm, ConferenceForm,
        path='conference',
        http_method='POST',
        name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(
        CONF_POST_REQUEST,
        ConferenceForm,
        path='conference/{websafeConferenceKey}',
        http_method='PUT',
        name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(
        CONF_GET_REQUEST,
        ConferenceForm,
        path='conference/{websafeConferenceKey}',
        http_method='GET',
        name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(
        message_types.VoidMessage,
        ConferenceForms,
        path='getConferencesCreated',
        http_method='POST',
        name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = self._getProfileFromUser()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[
                self._copyConferenceToForm(conf, getattr(prof, 'displayName'))
                for conf in confs
            ]
        )

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(
            request.filters, FIELDS
        )

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(
                filtr["field"], filtr["operator"], filtr["value"]
            )
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters, fields):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {
                field.name: getattr(f, field.name) for field in f.all_fields()
            }

            try:
                filtr["field"] = fields[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator."
                )

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous
                # filters
                # disallow the filter if inequality was performed on a
                # different field before
                # track the field on which the inequality operation is
                # performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field."
                    )
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(
        ConferenceQueryForms,
        ConferenceForms,
        path='queryConferences',
        http_method='POST',
        name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [
            (ndb.Key(Profile, conf.organizerUserId)) for conf in conferences
        ]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
            items=[
                self._copyConferenceToForm(conf, names[conf.organizerUserId])
                for conf in conferences
            ]
        )

# - - - Speaker objects - - - - - - - - - - - - - - - - -

    def _copySpeakerToForm(self, speaker, sessions=None):
        """Copy relevant fields from Speaker to SpeakerForm."""
        sf = SpeakerForm()
        for field in sf.all_fields():
            if hasattr(speaker, field.name):
                setattr(sf, field.name, getattr(speaker, field.name))
            elif field.name == "websafeKey":
                setattr(sf, field.name, speaker.key.urlsafe())
            elif field.name == "sessions" and sessions is not None:
                setattr(sf, field.name, sessions)
        sf.check_initialized()
        return sf

    def _createSpeakerObject(self, request):
        """Create or update Speaker object, returning SpeakerForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        if not request.name:
            raise endpoints.BadRequestException(
                "Speaker 'name' field required"
            )

        # copy SpeakerForm/ProtoRPC Message into dict
        data = {
            field.name: getattr(request, field.name)
            for field in request.all_fields()
        }
        del data['websafeKey']
        del data['sessions']

        # generate Speaker Key
        s_id = Speaker.allocate_ids(size=1)[0]
        s_key = ndb.Key(Speaker, s_id)
        data['key'] = s_key

        # create Speaker & return (modified) SpeakerForm
        Speaker(**data).put()
        return self._copySpeakerToForm(s_key.get())

    @endpoints.method(
        SpeakerForm,
        SpeakerForm,
        path='speaker',
        http_method='POST',
        name='createSpeaker')
    def createSpeaker(self, request):
        """Create new speaker"""
        return self._createSpeakerObject(request)

    @endpoints.method(
        message_types.VoidMessage,
        SpeakerForms,
        path='speakers',
        http_method='GET',
        name='getSpeakers')
    def getSpeakers(self, request):
        """Get list of speakers."""

        # create ancestor query for all key matches for this user
        speakers = Speaker.query()
        # return set of SpeakerForm objects per Speaker
        return SpeakerForms(
            items=[self._copySpeakerToForm(speaker) for speaker in speakers]
        )

# - - - Session objects - - - - - - - - - - - - - - - - -

    def _copySessionToForm(self, session):
        """Copy relevant fields from Session to SessionForm."""
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(session, field.name):
                # convert date and startTime to string; just copy others
                if field.name in ['date', 'startTime']:
                    setattr(sf, field.name, str(getattr(session, field.name)))
                else:
                    setattr(sf, field.name, getattr(session, field.name))
            elif field.name == "websafeKey":
                setattr(sf, field.name, session.key.urlsafe())
            elif field.name == "websafeSpeakerKey":
                setattr(sf, field.name, session.speakerKey.urlsafe())
        sf.check_initialized()
        return sf

    def _createSessionObject(self, request):
        """Create or update Session object, returning SessionForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException(
                "Session 'name' field required"
            )

        if not request.websafeConferenceKey:
            raise endpoints.BadRequestException(
                "Session 'websafeConferenceKey' field required "
            )

        try:
            c_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'websafeConferenceKey seems to be invalid')
        # check that conference exists
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with: %s' % request.websafeConferenceKey)

        # check if speaker entity exists
        try:
            sp_key = ndb.Key(urlsafe=request.websafeSpeakerKey)
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'websafeSpeakerKey seems to be invalid')
        speaker = sp_key.get()
        if not speaker:
            raise endpoints.NotFoundException(
                'No speaker found with key: %s' % request.websafeSpeakerKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can add sessions to the conference.')

        # copy SessionForm/ProtoRPC Message into dict
        data = {
            field.name:
                getattr(request, field.name) for field in request.all_fields()
        }
        del data['websafeKey']
        del data['websafeConferenceKey']
        del data['websafeSpeakerKey']

        # convert dates from strings to Date objects;
        # set month based on start_date
        if data['date']:
            data['date'] = datetime.strptime(
                data['date'][:10], "%Y-%m-%d"
            ).date()

        # convert time from strings to Time object
        if data['startTime']:
            data['startTime'] = datetime.strptime(
                data['startTime'][:5], "%H:%M"
            ).time()

        # set speaker key
        data['speakerKey'] = sp_key

        # generate Session Key based on Conference
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key

        # create Session, send email to organizer confirming
        # creation of Session & return (modified) SessionForm
        Session(**data).put()

        taskqueue.add(
            params={
                'email': user.email(),
                'sessionInfo': repr(request)
            },
            url='/tasks/send_confirmation_session_email'
        )

        taskqueue.add(
            params={
                'websafeConferenceKey': request.websafeConferenceKey,
                'websafeSpeakerKey': request.websafeSpeakerKey
            },
            url='/tasks/set_featured_speaker'
        )
        return self._copySessionToForm(s_key.get())

    @endpoints.method(
        SESSION_POST_REQUEST,
        SessionForm,
        path='conference/{websafeConferenceKey}/session',
        http_method='POST',
        name='createSession')
    def createSession(self, request):
        """Create new session"""
        return self._createSessionObject(request)

    @endpoints.method(
        CONF_GET_REQUEST,
        SessionForms,
        path='conference/{websafeConferenceKey}/sessions',
        http_method='GET',
        name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Get list of conference sessions."""

        # check for existing conference
        try:
            c_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'websafeConferenceKey seems to be invalid')
        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with: %s' % request.websafeConferenceKey)

        # create ancestor query for all key matches for this user
        sessions = Session.query(ancestor=c_key)
        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(session) for session in sessions]
        )

    @endpoints.method(
        SESSION_GET_REQUEST,
        SessionForms,
        path='conference/{websafeConferenceKey}/sessions/type/{typeOfSession}',
        http_method='GET',
        name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Get list of conference sessions filtered by type of session."""

        # check for existing conference
        try:
            c_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'websafeConferenceKey seems to be invalid')

        conf = c_key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with: %s' % request.websafeConferenceKey)

        # create ancestor query for all key matches for this user
        # filter by type of session
        sessions = Session.query(
            Session.typeOfSession == request.typeOfSession,
            ancestor=c_key
        )

        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(session) for session in sessions]
        )

    @endpoints.method(
        SPEAKER_GET_REQUEST,
        SessionForms,
        path='sessions/{websafeSpeakerKey}',
        http_method='GET',
        name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """Get list of conferences sessions filtered by speaker websafe key."""

        # filter by speaker
        try:
            s_key = ndb.Key(urlsafe=request.websafeSpeakerKey)
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'websafeSpeakerKey seems to be invalid')

        sessions = Session.query(Session.speakerKey == s_key)

        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(session) for session in sessions]
        )

    @endpoints.method(
        WISHLIST_POST_REQUEST,
        BooleanMessage,
        path='session/wishlist/{sessionKey}',
        http_method='POST',
        name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """Add session to user's whishlist."""

        prof = self._getProfileFromUser()  # get user Profile

        # check if session exists given sessionKey
        # get session; check that it exists
        try:
            s_key = ndb.Key(urlsafe=request.sessionKey)
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'sessionKey seems to be invalid')
        session = s_key.get()
        if not session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % request.sessionKey)

        # check if session already in wishlist
        if s_key in prof.sessionKeysWishList:
            raise ConflictException(
                "You have already add this session to your wishlist")

        # register user, take away one seat
        try:
            prof.sessionKeysWishList.append(s_key)
            prof.put()
        except db.BadValueError:
            raise endpoints.BadRequestException("Invalid Session key")

        return BooleanMessage(data=True)

    @endpoints.method(
        message_types.VoidMessage,
        SessionForms,
        path='sessions/wishlist',
        http_method='GET',
        name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Get user's sessions wishlist."""

        prof = self._getProfileFromUser()  # get user Profile
        sessions = ndb.get_multi(prof.sessionKeysWishList)

        # return set of SessionForm objects per Session
        return SessionForms(
            items=[
                self._copySessionToForm(s) for s in sessions if s is not None
            ]
        )

    @endpoints.method(
        message_types.VoidMessage,
        SessionForms,
        path='non-workshops-before-19',
        http_method='GET',
        name='getBefore19NonWorkshops')
    def getBefore19NonWorkshops(self, request):
        """Get list of non-workshop sessions which starts before 19 ."""

        # filter by start time
        sessions = Session.query(Session.startTime <= time(hour=19))
        # filter result by session type
        sessions = [s for s in sessions if s.typeOfSession != 'workshop']
        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(session) for session in sessions]
        )

    def _getSessionsQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Session.query()
        inequality_filter, filters = self._formatFilters(
            request.filters, SESSION_FIELDS
        )

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Session.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Session.name)

        for filtr in filters:
            if filtr["field"] == "duration":
                filtr["value"] = int(filtr["value"])

            formatted_query = ndb.query.FilterNode(
                filtr["field"], filtr["operator"], filtr["value"]
            )
            q = q.filter(formatted_query)
        return q

    @endpoints.method(
        QueryForms,
        SessionForms,
        path='querySessions',
        http_method='POST',
        name='querySessions')
    def querySessions(self, request):
        """Query for sessions."""
        sessions = self._getSessionsQuery(request)

        # return individual SessionForm object per Session
        return SessionForms(
                items=[self._copySessionToForm(s) for s in sessions]
        )

# - - - Featured Speaker - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheFeaturedSpeaker(websafeConferenceKey, websafeSpeakerKey):
        """Create Featured Speaker & assign to memcache;"""

        featured_speaker = ""

        # retrieve conference
        try:
            c_key = ndb.Key(urlsafe=websafeConferenceKey)
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'websafeConferenceKey seems to be invalid')
        conf = c_key.get()

        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % websafeConferenceKey)

        # set as featured speaker if speaker has at least 2 sessions
        try:
            s_key = ndb.Key(urlsafe=websafeSpeakerKey)
        except TypeError:
            raise endpoints.BadRequestException(
                'Only string is allowed as urlsafe input')
        except ProtocolBufferDecodeError:
            raise endpoints.BadRequestException(
                'websafeSpeakerKey seems to be invalid')

        sessions = Session.query(Session.speakerKey == s_key, ancestor=c_key)

        if len(list(sessions)) > 1:
            featured_speaker = {
                'speaker': s_key.get(),
                'sessions': [session.name for session in sessions]
            }
            memcache.set(MEMCACHE_FEATURED_SPEAKER_KEY, featured_speaker)

    @endpoints.method(
        message_types.VoidMessage,
        SpeakerForm,
        path='speaker/features',
        http_method='GET',
        name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Return Featured Speaker from memcache."""
        fs = memcache.get(MEMCACHE_FEATURED_SPEAKER_KEY)
        if fs:
            return self._copySpeakerToForm(fs['speaker'], fs['sessions'])
        return SpeakerForm()

# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(
                        pf,
                        field.name,
                        getattr(TeeShirtSize, getattr(prof, field.name))
                    )
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore or create a new one"""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(
        message_types.VoidMessage,
        ProfileForm,
        path='profile',
        http_method='GET',
        name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(
        ProfileMiniForm,
        ProfileForm,
        path='profile',
        http_method='POST',
        name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)

# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(
        message_types.VoidMessage,
        StringMessage,
        path='conference/announcement/get',
        http_method='GET',
        name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(
            data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or ""
        )

# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(
        message_types.VoidMessage,
        ConferenceForms,
        path='conferences/attending',
        http_method='GET',
        name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user Profile
        conf_keys = [
            ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend
        ]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [
            ndb.Key(Profile, conf.organizerUserId)
            for conf in conferences if conf is not None
        ]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[
                self._copyConferenceToForm(conf, names[conf.organizerUserId])
                for conf in conferences if conf is not None
            ]
        )

    @endpoints.method(
        CONF_GET_REQUEST,
        BooleanMessage,
        path='conference/{websafeConferenceKey}',
        http_method='POST',
        name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(
        CONF_GET_REQUEST,
        BooleanMessage,
        path='conference/{websafeConferenceKey}',
        http_method='DELETE',
        name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)

    @endpoints.method(
        message_types.VoidMessage,
        ConferenceForms,
        path='filterPlayground',
        http_method='GET',
        name='filterPlayground')
    def filterPlayground(self, request):
        """Filter Playground"""
        q = Conference.query()
        q = q.filter(Conference.city == "London")
        q = q.filter(Conference.topics == "Medical Innovations")
        q = q.filter(Conference.month == 6)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )

api = endpoints.api_server([ConferenceApi])  # register API

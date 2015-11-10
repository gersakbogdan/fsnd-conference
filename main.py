#!/usr/bin/env python

"""
main.py -- Udacity conference server-side Python App Engine
    HTTP controller handlers for memcache & task queue access

$Id$

created by wesc on 2014 may 24

"""

import webapp2
from google.appengine.api import app_identity
from google.appengine.api import mail
from conference import ConferenceApi

__author__ = 'wesc+api@google.com (Wesley Chun)'


class SetAnnouncementHandler(webapp2.RequestHandler):
    def get(self):
        """Set Announcement in Memcache."""
        ConferenceApi._cacheAnnouncement()
        self.response.set_status(204)


class SetFeaturedSpeakerHandler(webapp2.RequestHandler):
    def post(self):
        """Set Featured Speaker in Memcache."""
        ConferenceApi._cacheFeaturedSpeaker(
            websafeConferenceKey=self.request.get('websafeConferenceKey'),
            speaker=self.request.get('speaker')
        )


class SendConfirmationEmailHandler(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Conference creation."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Conference!',            # subj
            'Hi, you have created a following '         # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conferenceInfo')
        )


class SendConfirmationSessionEmailHandler(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Conference Session creation."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Session!',            # subj
            'Hi, you have created a following '         # body
            'session:\r\n\r\n%s' % self.request.get('sessionInfo')
        )

app = webapp2.WSGIApplication([
    ('/crons/set_announcement', SetAnnouncementHandler),
    ('/tasks/send_confirmation_email', SendConfirmationEmailHandler),
    ('/tasks/send_confirmation_session_email',
        SendConfirmationSessionEmailHandler),
    ('/tasks/set_featured_speaker', SetFeaturedSpeakerHandler)
], debug=True)

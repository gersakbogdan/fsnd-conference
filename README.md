## Udacity FSND -  P4 Conference Organization App
Udacity Full Stack Web Developer Nanodegree P4 Conference Organization App Project

### Setup Instructions
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
1. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
1. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
1. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
1. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting your local server's address (by default [localhost:8080][5].)
1. (Optional) Generate your client library(ies) with [the endpoints tool][6].
1. Deploy your application.

### Access
1. [Api Explorer](https://aqueous-argon-867.appspot.com/_ah/api/explorer)

### Implementation Details
* Add Sessions to Conference
    * Enpoints implemented:
        * getConferenceSessions(websafeConferenceKey) -- Given a conference, return all sessions
        * getConferenceSessionsByType(websafeConferenceKey, typeOfSession) Given a conference, return all sessions of a specified type (eg lecture, keynote, workshop)
        * getSessionsBySpeaker(speaker) -- Given a speaker, return all sessions given by this particular speaker, across all conferences
        * createSession(SessionForm, websafeConferenceKey) -- open only to the organizer of the conference

### Resources
* **Udacity course**
    * [Developing Scalable Apps in Python](https://www.udacity.com/course/developing-scalable-apps-in-python--ud858)
* Google Cloud Platform
    * [Google App Engine](https://developers.google.com/appengine)
    * [Google Cloud Endpoints](https://developers.google.com/appengine/docs/python/endpoints/)
    * [Google Developer Console](https://console.developers.google.com/)

[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
[7]: https://aqueous-argon-867.appspot.com

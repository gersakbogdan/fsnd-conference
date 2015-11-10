## Udacity FSND -  P4 Conference Organization App
Udacity Full Stack Web Developer Nanodegree [P4 Conference Organization App Project][7]

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

### Access this repository
1. [API Explorer](https://aqueous-argon-867.appspot.com/_ah/api/explorer)

### Implementation Details

#### Add Sessions to Conference
* Endpoints:
    * **getConferenceSessions(websafeConferenceKey)** -- Given a conference, return all sessions
    * **getConferenceSessionsByType(websafeConferenceKey, typeOfSession)** Given a conference, return all sessions of a specified type (eg lecture, keynote, workshop)
    * **getSessionsBySpeaker(speaker)** -- Given a speaker, return all sessions given by this particular speaker, across all conferences
    * **createSession(SessionForm, websafeConferenceKey)** -- open only to the organizer of the conference

* Session model:
    * name (StringProperty, required)
    * highlights (StringProperty)
    * speaker (StringProperty, required)
    * duration (IntegerProperty)
    * typeOfSession (StringProperty)
    * date (DateProperty)
    * startTime (TimeProperty)

Basically all Session model fields are required but sometimes at the beginning you don't have any information about a session
so I decided to set as required only the name and the speaker fields. As an improvement default values can be set.
Here the speaker field represents the Speaker websafeKey and not the name.

* Speaker model:
    * name (StringProperty, required)
    * about (StringProperty)

By using a model for the Speaker we have the opportunity to add more interesting features to the app later, like:
How many speakers we have, Which are the most popular, How long usually their session takes, etc.

#### Work on indexes and queries
* Endpoints:
    * **querySessions()** -- Filter sessions by name, speaker, duration or type of session

Using a general query/filter method requires new indexes on Session. **index.yaml** file contains a list of available indexes.

This filter will give you for example the opportunity to get only the sessions for which the type is workshop, takes more than 5 mins and where the speaker is one of your favourites.

Take note that only one inequality filter for multiple properties can be used:
"Limitations: The Datastore enforces some restrictions on queries. Violating these will cause it to raise exceptions. For example, combining too many filters, using inequalities for multiple properties, or combining an inequality with a sort order on a different property are all currently disallowed." ([read more][8])

One option to avoid this limitation is to apply only one inequality filter in the query and all the others in the code. Check "getBefore19Workshops" for an implementation example.

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
[8]: https://cloud.google.com/appengine/docs/python/ndb/queries

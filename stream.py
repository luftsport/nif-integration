import sys
import dateutil.parser
import json
import pymongo
import requests
from dateutil import tz

from eve_api import EveJSONEncoder
from eve_api import ChangeStreamItem
from nif_api import NifApiIntegration, NifApiCompetence, NifApiPayments
from settings import (
    ACLUBU,
    ACLUBP,
    API_URL,
    API_HEADERS,
    STREAM_RESUME_TOKEN_FILE,
    NIF_FEDERATION_USERNAME,
    NIF_FEDERATION_PASSWORD,
    STREAM_GEOCODE,
    NIF_REALM,
    NLF_ORG_STRUCTURE,
    STREAM_LOG_FILE
)

from pathlib import Path
from app_logger import AppLogger

if STREAM_GEOCODE:
    from geocoding import add_person_location, add_organization_location


class NifStream:
    """
    Processes change messages and inserts or updates the corresponding object in api.

    .. danger::
        Private members are also documented. :py:meth:`.run` and :py:meth:`.slow` are the publicly available
        methods.

    Handles the following NIF entity_types:

    * Person        :py:class:`typings.person.Person`
    * Function      :py:class:`typings.function.Function`
    * Organization  :py:class:`typings.organization.Organization`
    * Competence    :py:class:`typings.competence.Competence`
    * License       :py:class:`typings.license.License`

    :py:meth:`.run` uses :py:meth:`pymongo.MongoClient.watch` context to read the oplog change stream and react on each
    inserts. :py:meth:`.run` will check :py:attr:`.resume_token` in :py:attr:`.resume_token_path`
    and try to resume if exists and valid. :py:meth:`.run` will block forever or until :py:attr:`max_restarts`
    is reached.

    .. caution::

        If :py:attr:`resume_token` is out of date or mismatches the oplog, it will be deleted and will not be able to
        resume.

    .. note::

        To address errors like shutdowns or :py:attr:`.resume_token` out of date the class implements :py:meth:`.slow`
        to automatically try to address the errors by getting change messages through :py:mod:`eve_api`.

    Usage::

        from stream import NifStream
        stream = NifStream()
        stream.recover(errors=False)  # fix remaining change messages
        stream.run()  # Blocks forever

    """

    def __init__(self):

        self.log = AppLogger(name='nif-stream', stdout=False, last_logs=0, restart=True)

        self.restarts = 0
        self.max_restarts = 10
        self.token_reset = False

        self.resume_token = None
        self.resume_token_path = Path(STREAM_RESUME_TOKEN_FILE)
        self.resume_token_lock = False

        self.tz_local = tz.gettz("Europe/Oslo")
        self.tz_utc = tz.gettz('UTC')

        # Lungo Api
        self.api_collections = {
            'Person': {'url': '{}/persons/process'.format(API_URL), 'id': 'id'},
            'Function': {'url': '{}/functions/process'.format(API_URL), 'id': 'id'},
            'Organization': {'url': '{}/organizations/process'.format(API_URL), 'id': 'id'},
            'Competence': {'url': '{}/competences/process'.format(API_URL), 'id': 'id'},
            'License': {'url': '{}/licenses/process'.format(API_URL), 'id': 'id'},
            'Payment': {'url': '{}/payments/process'.format(API_URL), 'id': 'id'},
            'Changes': {'url': '{}/integration/changes'.format(API_URL), 'id': 'id'}

        }

        # NIF Api's
        self.api_license = NifApiIntegration(username=NIF_FEDERATION_USERNAME,
                                             password=NIF_FEDERATION_PASSWORD,
                                             log_file=STREAM_LOG_FILE,
                                             realm=NIF_REALM)

        self.api_competence = NifApiCompetence(username=NIF_FEDERATION_USERNAME,
                                               password=NIF_FEDERATION_PASSWORD,
                                               log_file=STREAM_LOG_FILE,
                                               realm=NIF_REALM)

        self.api_payments = NifApiPayments(username=ACLUBU,
                                           password=ACLUBP,
                                           log_file=STREAM_LOG_FILE,
                                           realm=NIF_REALM)

        self.api = NifApiIntegration(username=ACLUBU,
                                     password=ACLUBP,
                                     log_file=STREAM_LOG_FILE,
                                     realm=NIF_REALM)



        status, hello = self.api._test()
        if status is not True:
            self.log.error('[TERMINATING] Problems with NIF authentication')
            sys.exit(0)

        # Change stream
        client = pymongo.MongoClient()
        self.db = client.ka

    def recover(self, errors=False, realm=NIF_REALM):
        """Get change messages with status:

        errors=True
        * pending
        * error

        errors=False
        * ready

        via :py:mod:`eve_api` and process the messages in :py:meth:`._process_change`

        Sets the :py:attr:`.resume_token_lock` to avoid writing a :py:attr:`.resume_token` on updates.
        """
        r = False
        self.resume_token_lock = True
        if errors is True:
            try:
                r = requests.get(
                    '%s?where={"_status": {"$in": ["pending", "error"]},"_realm":"%s"}&max_results=100000' %
                    (self.api_collections['Changes']['url'], realm),
                    headers=API_HEADERS)
            except Exception as e:
                self.log.exception('Exception getting error and pending changes in recover')
        else:
            try:
                r = requests.get('%s?where={"_status": {"$in": ["ready"]},"_realm":"%s"}&max_results=100000' %
                                 (self.api_collections['Changes']['url'], realm),
                                 headers=API_HEADERS)
            except Exception as e:
                self.log.exception('Exception getting ready changes in recover')

        if r and r.status_code == 200:

            slow = r.json()

            for change in slow['_items']:
                self._process_change(ChangeStreamItem(change))

        self.resume_token_lock = False

    def _process_change(self, change) -> bool:
        """
        Process a change message. Will call the equivalent `_get_<entity_type>` method corresponding to the entity_type
        of the change message.

        Each of the methods will in turn call and return :py:meth:`._process` with correct payload.

        :param change: the change message
        :type change: dict
        :return: True on success
        :rtype: bool
        """

        status = False

        if change.set_status('pending'):
            try:
                # Get object from nif_api
                if change.entity_type == 'Person':
                    status, result = self.api.get_person(change.get_id())

                elif change.entity_type == 'Function':
                    status, result = self.api.get_function(change.get_id())

                elif change.entity_type == 'Organization':
                    status, result = self.api.get_organization(change.get_id(), NLF_ORG_STRUCTURE)

                elif change.entity_type == 'License':
                    status, result = self.api_license.get_license(change.get_id())

                elif change.entity_type == 'Competence':
                    status, result = self.api_competence.get_competence(change.get_id())

                elif change.entity_type == 'Payment':
                    status, result = self.api_payments.get_payment(change.get_id())

                # Insert into Lungo api
                if status is True:
                    pstatus, pmessage = self._process(result, change)
                    if pstatus is True:  # Sets the change message status
                        change.set_status('finished')
                        return True
                    else:
                        change.set_status('error', pmessage)

                else:
                    self.log.error('NIF API error for {} ({}) change message: {}'.format(change.entity_type,
                                                                                         change.id,
                                                                                         change._id))
                    change.set_status('error', 'Got http {} for {} {}'.format(status,
                                                                              change.entity_type,
                                                                              change.get_id()))  # Error in nif_api

            except Exception as e:
                self.log.exception('Error in process change')
                change.set_status('error', {'exception': str(e)})
        else:
            self.log.error('Cant change Person status to pending')
            raise Exception('Cant change Person status to pending')

        return False

    def run(self):
        """Read the mongo change stream

        On all `insert` operations to `integration/changes` we retrieve the full document (change message) and act
        accordingly via :py:meth:`_process_change`

        .. note::
            Starting with MongoDB 4.2 `startAfter` will be replaced by `resumeAfter` which will resume on errors
            unlike current behaviour of `resumeAfter`

        """

        self.log.debug('[Stream started]')
        self._read_resume_token()

        if self.resume_token is not None:
            resume_after = {'_data': self.resume_token}
            self.log.debug('Got resume token')
        else:
            resume_after = None
            self.log.debug('No resume token')

        try:
            # @TODO on upgrade to mongo 4.2 use startAfter instead
            self.log.debug('Change stream watch starting...')
            with self.db.integration_changes.watch(pipeline=[{'$match': {'operationType': 'insert'}}],
                                                   resume_after=resume_after) as stream:

                for change in stream:
                    if change['fullDocument']['_realm'] == NIF_REALM:
                        self.log.debug('Processing change message: {} {}'.format(change['fullDocument']['entity_type'],
                                                                                 change['fullDocument']['id']))

                        # Always set new resume token
                        self.resume_token = change['_id']['_data']

                        if self._process_change(ChangeStreamItem(change['fullDocument'])) is True:
                            self.log.debug('Successfully processed')
                            self._write_resume_token()

                self.restarts = 0

        except pymongo.errors.PyMongoError as e:
            self.log.error('Unrecoverable PyMongoError, restarting')
            self.restarts += 1
            if self.restarts > self.max_restarts:
                self.log.error('Too many retries')
                pass
            else:
                self.run()

        except Exception as e:
            self.log.exception('Unknown error in change stream watch')

            self.restarts += 1
            if self.restarts > self.max_restarts:
                self.log.error('Too many restarts: {}'.format(self.restarts))

                if not self.token_reset:
                    self.log.error('Resetting resume token')
                    self._reset_token()
                    self.run()
            elif not self.token_reset:
                self.run()

    def _merge_dicts(self, x, y):
        """Simple and safe merge dictionaries

        :param x: first dictionary
        :type x: dict
        :param y: second dictionary
        :type y: dict
        :return: merged dict z
        :rtype: dict
        """
        z = x.copy()  # start with x's keys and values
        z.update(y)  # modifies z with y's keys and values & returns None

        return z

    def _merge_user_to(self, id, merged):
        """Update all persons in api which ``id`` is merged from.

        .. note::
            NIF describes ``merged_from`` which makes no sense. For the api to be able to hand out a 301 each object
            merged to ``id`` needs a ``merged_to: id``. This can be acted upon and resolves unlimited levels of merging.

        :param id: Person id
        :type id: int
        :param merged: List of person id's merged from to id
        :type merged: list[int]
        :return: None
        :rtype: None
        """

        if len(merged) > 0:

            for m in merged:

                u = requests.get('%s/%s' % (self.api_collections['Person']['url'], m),
                                 headers=API_HEADERS)

                if u.status_code == 200:
                    u_json = u.json()

                    u_u = requests.patch('%s/%s' % (self.api_collections['Person']['url'], u_json['_id']),
                                         json={'_merged_to': id},
                                         headers=self._merge_dicts(API_HEADERS, {'If-Match': u_json['_etag']}))

                    if u_u.status_code == 200:
                        pass
                elif u.status_code == 404:
                    """Not found, create a user!"""
                    u_p = requests.post(self.api_collections['Person']['url'],
                                        json={'id': m, '_merged_to': id},
                                        headers=API_HEADERS)

                    if u_p.status_code != 201:
                        self.log.error('Error merge to ', u_p.text)

    def _write_resume_token(self):
        """Writes the current :py:attr:`resume_token` to :py:attr:`resume_token_path` file"""

        if self.resume_token_lock is not True:

            try:
                with open(STREAM_RESUME_TOKEN_FILE, 'w+') as f: # removed binary b
                    f.write(self.resume_token)
            except Exception as e:
                self.log.exception('Could not write resume token')

    def _read_resume_token(self):
        """Reads the value of :py:attr:`resume_token_path` file into :py:attr:`resume_token`"""
        try:
            with open(STREAM_RESUME_TOKEN_FILE, 'r') as f: # removed binary b
                self.resume_token = f.read()
        except FileNotFoundError:
            self.resume_token = None
        except:
            self.log.exception('Error reading resume token')
            self.resume_token = None

    def _reset_token(self, delete=True):
        """Deletes or truncates the :py:attr:`resume_token_path` file

        :param delete: If True then delete file, else truncate
        :type delete: bool
        """

        if delete is True:
            try:
                self.resume_token_path.unlink()
            except:
                self.log.exception('Could not delete resume token')
        else:
            try:
                with open(STREAM_RESUME_TOKEN_FILE, 'wb+') as f:
                    f.write('')
            except:
                self.log.exception('Could not truncate resume token')

        self.token_reset = True

    def _process(self, payload, change):
        """
        Update or create a document based on ``payload``

        :param payload: The payload for the document
        :type payload: dict
        :param change: The change object
        :type change: ChangeStreamItem
        :return: True on success
        :rtype: bool
        """
        api_document = requests.get('%s/%s' % (self.api_collections[change.get_value('entity_type')]['url'],
                                               payload[self.api_collections[change.get_value('entity_type')]['id']]),
                                    headers=API_HEADERS)
        rapi = False

        # Does not exist, insert
        if api_document.status_code == 404:

            # Geocode
            if change.get_value('entity_type') == 'Person' and STREAM_GEOCODE is True:
                payload = add_person_location(payload)
            elif change.get_value('entity_type') == 'Organization' and STREAM_GEOCODE is True:
                payload = add_organization_location(payload)

            rapi = requests.post(self.api_collections[change.get_value('entity_type')]['url'],
                                 data=json.dumps(payload, cls=EveJSONEncoder),
                                 headers=API_HEADERS)

        # Do exist, replace
        elif api_document.status_code == 200:

            api_existing_object = api_document.json()

            # Only update if newer
            # if dateutil.parser.parse(api_existing_object['_updated']) < change.get_modified().replace(tzinfo=self.tz_local):

            # Geocode Person
            if change.get_value('entity_type') == 'Person' and STREAM_GEOCODE is True:
                payload = add_person_location(payload)

            # Really need to preserve the activities for clubs type_id 5
            if change.get_value('entity_type') == 'Organization' and payload.get('type_id', 0) == 5:
                payload.pop('activities', None)
                payload.pop('main_activity', None)
                rapi = requests.patch('%s/%s' % (self.api_collections[change.get_value('entity_type')]['url'],
                                                 api_existing_object['_id']),
                                      data=json.dumps(payload, cls=EveJSONEncoder),
                                      headers=self._merge_dicts(API_HEADERS,
                                                                {'If-Match': api_existing_object['_etag']})
                                      )
            else:
                rapi = requests.put('%s/%s' % (self.api_collections[change.get_value('entity_type')]['url'],
                                               api_existing_object['_id']),
                                    data=json.dumps(payload, cls=EveJSONEncoder),
                                    headers=self._merge_dicts(API_HEADERS,
                                                              {'If-Match': api_existing_object['_etag']})
                                    )

            # Disabled, ref check if newer
            # If obsolete, just return
            # else:
            #     change.set_status('finished')
            #     return True, None

        # If successful put or post
        if rapi.status_code in [200, 201]:

            if change.get_value('entity_type') == 'Person':

                rapi_json = rapi.json()

                # Add merged to for all merged from
                if len(change.merged_from) > 0:
                    self._merge_user_to(rapi_json['id'], change.merged_from)

            return True, None

        else:

            self.log.error('Error in _process for {} with id {} change {}'.format(change.get_value('entity_type'),
                                                                                  change.id,
                                                                                  change.get_value('_id')))
            self.log.error('Error: http {} said {}'.format(rapi.status_code, rapi.text))

            try:
                rapi_json = rapi.json()
                if '_issues' in rapi_json:
                    return False, rapi_json['_issues']
            except Exception as e:
                rapi_json = {
                    '_issues': {'message': 'Unknown error, got http {} with error {}'.format(rapi.status_code, str(e))}}

        return False, rapi_json.get('_issues', 'Unknown error line 442')


if __name__ == "__main__":
    sys.exit(0)

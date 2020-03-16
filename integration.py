import time
import json
import requests
from random import sample

from eve_api import EveJSONEncoder
from app_logger import AppLogger

from settings import NIF_INTEGRATION_URL, ACLUBP, ACLUBU, NIF_INTEGRATION_GROUPS_AS_CLUBS
from settings import (
    NIF_PLATFORM_PASSWORD,
    NIF_PLATFORM_USERNAME,
    NIF_CLUB_FIRSTNAME_PREFIX,
    NIF_SYNC_URL,
    NIF_CLUB_USERNAME_PREFIX,
    API_URL,
    API_HEADERS,
    NIF_CLUB_APP_ID,
    NIF_INTEGRATION_FUNCTION_TYPE_ID,
    NLF_ORG_STRUCTURE,
    NIF_PLATFORM_FUNCTION_ID,
    NIF_REALM
)

from nif_api import NifApiIntegration, NifApiSynchronization


class NifIntegrationClientError(Exception):
    """Zeep client error"""


class NifIntegrationUserError(Exception):
    """Generic integration user error"""


class NifIntegrationUserCreateError(NifIntegrationUserError):
    """Zeep client returns :py:class:`zeep.exceptions.Fault` on user creation, api error"""


class NifIntegrationUserAuthenticationError(NifIntegrationUserError):
    """Integration user authentication error"""


class NifIntegrationUser:
    """Handles retrieving existing or creating new integration users for use with :py:mod:`sync.NifSync` and
    :py:mod:`stream.NifStream`

    .. attention::
        If a user do not exist, it will be created on init.

    .. note::
        This class only handles integration users on club level (org_type_id=5) and requires a platform user in NIF.

    .. attention::
        It might take up to (or more) than 180 seconds from creating a user before that user can be authenticated
    """

    def __init__(self, club_id, create_delay=1, log_file='integration_user.log'):

        self.ALPHNUM = (
                'abcdefghijklmnopqrstuvwxyz' +
                'ABCDEFGHIJKLMNOPQRSTUVWXYZ' +
                '01234567890'
        )

        self.username = None
        self.password = None
        self.nif_user = {}
        self.user_id = None
        self.club_created = None
        self.club_name = None
        self.log_file = log_file

        self.log = AppLogger('klubb-{0}'.format(club_id))

        self.log.debug('[Integration user]')

        self.club_id = club_id

        self.test_client = None

        api_user = requests.get(
            '%s/integration/users/?where={"club_id": %s, "_active": true, "_realm": "%s"}&max_results=1000' % (API_URL,
                                                                                                               self.club_id,
                                                                                                               NIF_REALM),
            headers=API_HEADERS)

        if api_user.status_code == 200:
            api_users_json = api_user.json()

            if len(api_users_json['_items']) > 1:  # multiple users
                self.log.error('More than one active club in realm {} for club id {}'.format(NIF_REALM, self.club_id))
                raise NifIntegrationUserError('More than one active club')

            elif len(api_users_json['_items']) == 1:  # One user only

                api_user_json = api_users_json['_items'][0]

                self.username = '{0}/{1}/{2}'.format(NIF_CLUB_APP_ID,
                                                     api_user_json['function_id'],
                                                     api_user_json['username'])

                self.password = api_user_json['password']
                self.user_id = api_user_json['id']
                self.log.debug('Using existing integration user {}'.format(self.username))

                if 'club_created' in api_user_json:
                    self.club_created = api_user_json['club_created']
                    self.club_name = api_user_json['club_name']
                else:
                    self.club_created, self.club_name = self._get_club_details()

                if create_delay > 0:
                    if self._time_authentication(create_delay=create_delay) is True:
                        self.log.debug('Authentication ok')
                    else:
                        # @TODO set user _active = False?
                        self.log.error('Failed authentication via Hello')
                        time.sleep(5)

            elif len(api_users_json['_items']) == 0:  # No users found but 200 anyway
                """Not found create user!"""
                self.log.debug('No existing integration user found but http 200, creating...')

                self.club_created, self.club_name = self._get_club_details()

                if self._create():
                    self.log.debug('Created integration user for club id {}'.format(self.club_id))

                    if create_delay > 0:
                        self._time_authentication(create_delay=create_delay)

                else:
                    raise NifIntegrationUserCreateError
            else:
                self.log.exception(
                    'Creation of user for club id {} failed, got {} users and http 200'.format(
                        self.club_id, len(api_users_json['_items'])))

        elif api_user.status_code == 404:
            """Not found create user!"""
            self.log.debug('No existing integration user found, creating...')

            self.club_created, self.club_name = self._get_club_details()

            if self._create():
                self.log.debug('Created integration user for club id {}'.format(self.club_id))

                # if create_delay > 0:
                #    self.log('Delaying {}s before proceeding'.format(create_delay))
                #    time.sleep(create_delay)

                # Test authentication of user
                # Only if create_delay > 0
                # This will try to loop in intervals until authenticated or timeout

                if create_delay > 0:
                    self._time_authentication(create_delay=create_delay)

            else:
                raise NifIntegrationUserCreateError

        else:
            self.log.exception('Unknown error')
            raise NifIntegrationUserError

    def _time_authentication(self, create_delay) -> bool:

        self.log.debug('Running auth test for {} with password {}'.format(self.username, self.password))

        authenticated = False
        time_spent = 0
        increment = 10

        while not authenticated:
            print('.')
            if time_spent > create_delay:
                self.log.debug('Could not authenticate user after {} seconds'.format(time_spent))
                raise NifIntegrationUserAuthenticationError('Can not authenticate user')

            authenticated = self.test_login()
            time.sleep(increment)
            time_spent += increment

            if time_spent > 220:
                self.log.debug('Could NOT authenticate user after {} seconds, exiting'.format(time_spent))
                break

        if authenticated:
            self.log.debug('Authenticated user after {} seconds'.format(time_spent))

        return authenticated

    def _get_club_details(self):

        response = requests.get('{}/organizations/{}'.format(API_URL, self.club_id),
                                headers=API_HEADERS)

        if response.status_code == 200:

            r = response.json()

            if 'created' in r and 'name' in r:
                return r['created'], r['name']

        return '1995-10-11T22:00:00.000000Z', 'Unknown name'

    def _create(self):
        """Creates an integration user applied to club_id
        Firstname: NLF<app id>-<club_id>
        Username: IGNLF<app_id>-<club_id>
        Only needs correct function Id
        User will end up as club user anyway"""

        sync_client = NifApiSynchronization(username=NIF_PLATFORM_USERNAME,
                                            password=NIF_PLATFORM_PASSWORD,
                                            realm=NIF_REALM,
                                            log_file=self.log_file)

        self.password = self.generate_password()
        club_username = '{0}-{1}'.format(NIF_CLUB_USERNAME_PREFIX, self.club_id)

        # Log user to be created
        self.log.debug('Creating integration user')
        self.log.debug('Club:   {}'.format(self.club_name))
        self.log.debug('User:   {}'.format(club_username))
        self.log.debug('Pwd:    {}'.format(self.password))

        # The exception is caught in the call to _create.
        status, self.nif_user = sync_client.create_integration_user(
            FirstName='{0}-{1}'.format(NIF_CLUB_FIRSTNAME_PREFIX,
                                       self.club_id),
            LastName='NIF.Connect',
            OrgId=self.club_id,
            Password=self.password,
            UserName=club_username)
        # Email=None)

        if status is True:

            self.log.debug('Created integration user {0} with password {1}'.format(club_username, self.password))

            # Get correct function id
            function_id = 0
            if 'ActiveFunctions' in self.nif_user and 'Function' in self.nif_user['ActiveFunctions']:

                for f in self.nif_user['ActiveFunctions']['Function']:

                    if (f['FunctionTypeId'] == NIF_INTEGRATION_FUNCTION_TYPE_ID
                            and f['ActiveInOrgId'] == self.club_id):
                        function_id = f['Id']
                        break  # break for

            # If no function id use platform function id which works.
            if function_id == 0:
                function_id = NIF_PLATFORM_FUNCTION_ID

            # assign correct username and password
            self.username = '{0}/{1}/{2}'.format(NIF_CLUB_APP_ID,
                                                 function_id,
                                                 club_username)

            # Assign correct user_id
            if 'Id' in self.nif_user:
                self.user_id = self.nif_user['Id']  # Or PersonId?
            elif 'PersonId' in self.nif_user:
                self.user_id = self.nif_user['PersonId']
            else:
                self.log.error('Could not assign user_id to integration user')
                raise NifIntegrationUserCreateError

            # Store the integration user in Lungo
            payload = {'username': club_username,
                       'password': self.password,
                       'id': self.user_id,
                       'app_id': NIF_CLUB_APP_ID,
                       'function_id': function_id,
                       'club_id': self.club_id,
                       'club_name': self.club_name,
                       'modified': self.nif_user['LastChangedDate'],
                       'club_created': self.club_created,
                       '_realm': NIF_REALM,
                       '_active': True}

            api_user = requests.post('{}/integration/users'.format(API_URL),
                                     data=json.dumps(payload, cls=EveJSONEncoder),
                                     headers=API_HEADERS
                                     )
            if api_user.status_code == 201:
                self.log.debug('Successfully created user in Lungo')
                return True  # Instead of returning void, return something else
            else:
                self.log.error('Could not create user in Lungo')
                self.log.error('Code:   {}'.format(api_user.status_code))
                self.log.error('Msg:    {}'.format(api_user.text))
                raise NifIntegrationUserCreateError

        else:
            self.log.error(
                'Could not create integration user {0} with password {1}'.format(club_username, self.password))
            self.log.error('NIF Api said:')
            self.log.error('Code:   {}'.format(self.nif_user['ErrorCode']))
            self.log.error('Message:{}'.format(self.nif_user['ErrorMessage']))
            raise NifIntegrationUserCreateError

        return False

    def get_user(self):

        pass

    def generate_password(self, count=1, length=12):
        """ Generate password
        Kwargs:
            count (int)::
                How many passwords should be returned?
            length (int)::
                How many characters should the password contain
            allowed_chars (str)::
                Characters
        Returns:
            String with the password. If count > 1 then the return value will be auto_now=
            list of strings.
        """
        if count == 1:
            return ''.join(sample(self.ALPHNUM, length))

        passwords = []
        while count > 0:
            passwords.append(''.join(sample(self.ALPHNUM, length)))
            count -= 1

        return passwords


class NifIntegration:
    def __init__(self):

        pass

    def get_active_clubs_from_ka(self) -> [int]:
        r = requests.get(
            '{}/ka/clubs?max_results=10000&where={{"IsActive": true, "OrgTypeId": {{"$in": [5,6]}} }}'.format(API_URL),
            headers=API_HEADERS)

        if r.status_code == 200:
            resp = r.json()

            if '_items' in resp:
                clubs = [d['Id'] for d in resp['_items']]
                return clubs

        return []

    def get_ka_clubs(self, active=True) -> [int]:

        r = requests.get('{}/ka/clubs?max_results=1000'.format(API_URL),
                         headers=API_HEADERS)

        if r.status_code == 200:
            resp = r.json()

            if '_items' in resp:
                clubs = [d['Id'] for d in resp['_items']]
                return clubs

        return []

    def get_club_list(self) -> [int]:

        r = requests.get('%s/organizations?where={"type_id":5}&max_results=1000' % API_URL,
                         headers=API_HEADERS)

        if r.status_code == 200:
            resp = r.json()

            if '_items' in resp:
                clubs = [d['id'] for d in resp['_items']]
                return clubs

        return []

    def get_clubs(self) -> [dict]:
        """Gets all clubs in organization"""

        r = requests.get('%s/organizations?where={"type_id":5, "is_active": true}&max_results=1000' % API_URL,
                         headers=API_HEADERS)

        if r.status_code == 200:
            resp = r.json()

            if '_items' in resp:
                clubs = [{'club_id': d['id'], 'created': d['created'], 'name': d['name']} for d in resp['_items']]
                for group in NIF_INTEGRATION_GROUPS_AS_CLUBS:
                    clubs.append({'club_id': group})
                return clubs

        return []

    def insert_clubs(self) -> None:
        """Gets clubs from KA then inserts into organization

        @TODO should rather use organization for these operations

        .. attention::
            This is a utility method, probably to be deferred anytime soon!
        """

        integration_client = NifApiIntegration(username=ACLUBU,
                                               password=ACLUBP,
                                               realm=NIF_REALM,
                                               log_file=self.log_file)

        for club_id in self.get_ka_clubs():

            status, org = integration_client.get_organization(club_id, NLF_ORG_STRUCTURE)

            if status is True:

                post = requests.post('{0}/organizations/process'.format(API_URL),
                                     data=json.dumps(org, cls=EveJSONEncoder),
                                     headers=API_HEADERS
                                     )
                # print('Type id', org['type_id'])
                if post.status_code == 201:
                    # print('Success')
                    pass
                elif post.status_code == 422:
                    # print('Already exists')
                    pass
                else:
                    # print('ERROR, ', post.status_code)
                    # print(post.text)
                    pass

            else:
                # print('Error with org')
                # print(org)
                # print('Club id', club_id)
                pass

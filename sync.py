"""
.. module:: NIF sync integration
    :platform: Unix
    :synopsis: Integration of change messages, NIF (soap) API -> NLF (Eve) API
"""

import sys
import threading
import time
from datetime import datetime, timedelta

import dateutil.parser
import hashlib
import json
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED, EVENT_JOB_ERROR
from dateutil import tz

from eve_api import EveJSONEncoder

from nif_api import NifApiSynchronization
from app_logger import AppLogger
from settings import (
    API_HEADERS, API_URL,
    STREAM_RESUME_TOKEN_FILE,
    NIF_POPULATE_INTERVAL,
    NIF_CHANGES_SYNC_INTERVAL,
    NIF_FEDERATION_USERNAME,
    NIF_FEDERATION_PASSWORD,
    NIF_LICENSE_SYNC_INTERVAL,
    LOCAL_TIMEZONE,
    NIF_REALM,
    SYNC_LOG_FILE,
    NIF_SYNC_DELAY,
    NIF_SYNC_MAX_ERRORS,
    NIF_SYNC_TYPES
)
from notifications import send_email


class FakeSemaphore(object):
    """A semaphore context to be able to run :py:class:`NifSync` without a specifying a semaphore
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._locked = False

    def __enter__(self):
        locked = self._lock.acquire(False)
        self._locked = locked
        return locked

    def __exit__(self, *args):
        if self._locked:
            self._lock.release()
            self._locked = False


class SyncState(object):
    state = 'Unknown'
    mode = 'Unknown'
    reason = ''

    def __init__(self, state='running', mode='init', reason='startup'):
        self._states = ['running', 'terminated', 'terminating', 'sleeping', \
                        'paused', 'resuming', 'finished', 'started', \
                        'initialized', 'waiting']
        self._modes = ['init', 'check', 'sync', 'populate']

        self.set_state(**{'state': state, 'mode': mode, 'reason': reason})

    def set_state(self, **kwargs) -> None:
        self.state = kwargs.get('state', None) if kwargs.get('state', None) in self._states else self.state
        self.mode = kwargs.get('mode', None) if kwargs.get('mode', None) in self._modes else self.mode
        self.reason = kwargs.get('reason', '')

    def get_state(self) -> dict:
        return {'state': self.state, 'mode': self.mode, 'reason': self.reason}


class NifSync(threading.Thread):
    """Populate and sync change messages from NIF api

    Currently handles following services and respective entity types:

    * SynchronizationService/GetChanges3:
        * Person
        * Function
        * Organization
    * SynchronizationService/GetChangesCompetence2:
        * Competence
    * SynchronizationService/GetChangesLicense:
        * License

    .. danger::
        The club (org_type_id=5) integration users can only use GetChanges3 ( :py:attr:`sync_type` ='changes'). For
        GetChangesCompetence2 ( :py:attr:`sync_type` ='competence') and
        GetChangesLicense ( :py:attr:`sync_type` = 'license') an integration user on federation level is required

    The class will automatically handle when to :py:meth:`populate` and :py:meth:`sync`.

    .. note::
        :py:meth:`_check` is called on init and checks with the api to find last change message for
        :py:attr:`org_id` and the last message is then used as the initial starting point.


    :param org_id: The integration user organization id, required
    :type org_id: int
    :param login: The full path integration username ('app_id/function_id/username'), required
    :type login: str
    :param password: Password, required
    :type password: str
    :param created: A datetime string representing creation date of org_id, required
    :type created: str
    :param stopper: a threading.Event flag to exit
    :type stopper: threading.Event
    :param restart: On True will reset all AppLogger handlers
    :type restart: bool
    :param background: Sets the scheduler. Defaults to False and BlockingScheduler
    :type background: bool
    :param initial_timedelta: The initial timedelta to use from last change message in ms
    :type initial_timedelta: int
    :param overlap_timedelta: A optional timedelta for overlap functions in hours
    :type overlap_timedelta: int
    :param lock: The semaphore object, if None uses :py:class:`.FakeSemaphore`
    :type lock: threading.BoundedSemaphore
    :param sync_type: The sync type for this user, allowed ``changes``, ``competence`` and ``license``. Defaults to ``changes``.
    :type sync_type: str
    :param sync_interval: The interval for the sync scheduler in minutes. Defaults to NIF_SYNC_INTERVAL
    :type sync_interval: int
    :param populate_interval: The interval for populating in days. Defaults to NIF_POPULATE_INTERVAL
    :type populate_interval: int

    Usage - threading::

        from sync import NifSync
        sync = NifSync(org_id, username, password)
        sync.start()  # sync is of threading.Thread

    Usage - blocking::

        from sync import NifSync
        sync = NifSync(org_id, username, password)
        sync.run()  # sync starts without thread running

    Usage - with semaphore::

        import threading
        from sync import NifSync
        bound_semaphore = threading.BoundedSemaphore(value=10)
        sync = NifSync(org_id, username, password, lock=bounding_semaphore)
        sync.start()  # sync is of threading.Thread, semaphore has 10 slots

    .. note::
        The usernames and passwords for integration users on club level is stored in integration/users and accessible
        through :py:mod:`
    """

    def __init__(self,
                 org_id,
                 username,
                 password,
                 created,
                 stopper=False,
                 restart=False,
                 background=False,
                 initial_timedelta=0,
                 overlap_timedelta=0,
                 lock=None,
                 sync_type='changes',
                 sync_interval=NIF_CHANGES_SYNC_INTERVAL,
                 populate_interval=NIF_POPULATE_INTERVAL):

        self.state = SyncState()

        # Init thread
        super().__init__(name='klubb-{0}'.format(org_id))

        if sync_type in NIF_SYNC_TYPES:
            self.sync_type = sync_type
        else:
            raise Exception('{} is not a valid sync type'.format(sync_type))

        self.id = org_id
        self.username = username

        self.started = datetime.now()
        self.sync_errors = 0
        # self.sync_errors_max = 3  # Errors in a row!

        self.sync_interval = sync_interval  # minutes
        self.populate_interval = populate_interval  # days

        self.initial_timedelta = initial_timedelta
        self.overlap_timedelta = overlap_timedelta

        self.messages = 0  # Holds number of successfully processed messages

        self.stopper = stopper
        self.background = background

        self.initial_start = None
        self.from_to = [None, None]
        self.sync_started = False

        self.tz_local = tz.gettz(LOCAL_TIMEZONE)
        self.tz_utc = tz.gettz('UTC')

        #  Init logger
        self.log = AppLogger(name='klubb-{0}'.format(org_id), stdout=not background, last_logs=100, restart=restart)

        # No stopper, started directly check for stream resume token!
        if self.stopper is False:
            from pathlib import Path
            resume_token = Path(STREAM_RESUME_TOKEN_FILE)

            if resume_token.is_file() is not True:
                self.log.warning('No resume token at {}'.format(STREAM_RESUME_TOKEN_FILE))
                self.log.warning('Requires stream to have or be running and a valid token file')

        if lock is not None and (isinstance(lock, threading.BoundedSemaphore) or isinstance(lock, threading.Semaphore)):
            self.lock = lock
        else:
            self.lock = FakeSemaphore()  # Be able to run singlethreaded as well

        # Lungo REST API
        self.api_integration_url = '%s/integration/changes' % API_URL

        # Make a startup log entry
        self.log.debug('[STARTUP]')
        self.log.debug('Org_id:     {0}'.format(org_id))
        self.log.debug('Login:      {0}'.format(username))
        self.log.debug('Pwd:        {0}'.format(password))
        self.log.debug('Created:    {0}'.format(created))
        self.log.debug('Skew:       {0} seconds'.format(self.initial_timedelta))
        self.log.debug('Sync:       {0} minutes'.format(self.sync_interval))
        self.log.debug('Populate:   {0} hours'.format(self.populate_interval))
        self.log.debug('Api url:    {0}'.format(self.api_integration_url))

        # Created
        self.org_created = dateutil.parser.parse(created)
        if self.org_created.tzinfo is None or self.org_created.tzinfo.utcoffset(self.org_created) is None:
            """self.org_created is naive, no timezone we assume CET"""
            self.org_created = self.org_created.replace(tzinfo=self.tz_local)

        self.org_id = org_id

        try:
            self.nif = NifApiSynchronization(username, password, realm=NIF_REALM, log_file=SYNC_LOG_FILE,
                                             test_login=False)
        except:
            self.log.exception('Sync client creation for {} failed, terminating'.format(username))
            # sys.exit(0)
            raise Exception('Could not create sync client')

        # Setup job scheduler
        if self.background:
            self.scheduler = BackgroundScheduler()
            self.log.info('Scheduler:  BackgroundScheduler')
        else:
            self.scheduler = BlockingScheduler()
            self.log.info('Scheduler:  BlockingScheduler')

        self.job_misfires = 0
        self.scheduler.add_listener(self._job_fire, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_misfire, EVENT_JOB_MISSED)

        self.job = self.scheduler.add_job(self.sync, 'interval', minutes=self.sync_interval, max_instances=1)

        self.state.set_state(state='finished')

    def __del__(self):
        """Destructor, shutdown the scheduler on exit"""

        try:
            self.log.debug('Destructor called, terminating thread')
        except:
            pass

        try:
            if self.scheduler.running is True:
                self.scheduler.shutdown(wait=False)
                self.log.debug('Shutting down scheduler')
        except:
            self.log.error('Could not shut down scheduler')
            send_email(subject='Sync shutdown failed', message='Sync could not shut down scheduler, line 289, for user {}'.format(self.username))
            pass

    @property
    def uptime(self) -> (int, int):
        """Calculate thread uptime

        :returns uptime: integer tuple (days, seconds) since thread start
        """

        t = datetime.now() - self.started
        return t.days, t.seconds

    @property
    def job_next_run_time(self):

        if self.scheduler.state == 1:
            return self.job.next_run_time

        return None

    def job_pause(self):

        if self.scheduler.state == 1:
            self.job.pause()

    def job_resume(self):

        if self.scheduler.state == 1:
            self.job.resume()

    @property
    def scheduler_state(self):

        return self.scheduler.state

    def _job_misfire(self, event) -> None:
        """Callback for failed job execution. Increases :py:attr:`job_misfires`

        :param event: apcscheduler.Event
        """
        self.job_misfires += 1

    def _job_fire(self, event) -> None:
        """Callback for succesfull job execution. Decreases :py:attr:`job_misfires`

        :param event: apcscheduler.Event
        """
        if self.job_misfires > 0:
            self.job_misfires -= 1

    def run(self) -> None:
        """Start the thread, conforms to threading.Thread.start()

        Calls :py:meth:`._check` which determines wether to run :py:meth:`populate` or start a job with target
        :py:meth:`sync`
        """
        self.log.debug('[Starting thread]')
        self._check()

    def _stopper(self, force=False) -> None:
        """If stopper is threading event and is set, then terminate"""

        # Check if too many errors
        if self.sync_errors >= NIF_SYNC_MAX_ERRORS:
            self.state.set_state(mode=self.state.mode, state='terminated', reason='too many errors')
            send_email(subject='Sync shutdown', message='Sync shut down scheduler, line 355, too many errors for user {}'.format(self.username))

            self._shutdown()  # because setting stopper propagates to all!

        if isinstance(self.stopper, threading.Event):

            if self.stopper.is_set():
                self.log.warning('Stopper is set, terminating thread')
                self._shutdown()

        if force is True:
            self.log.warning('Forcing shutdown, terminating thread')
            self._shutdown()

    def _shutdown(self) -> None:
        """Shutdown in an orderly fashion"""

        if self.scheduler.state > 0:
            try:
                self.log.debug('Shutting down scheduler')
                if self.scheduler.running is True:
                    self.scheduler.shutdown(wait=False)  # wait=False
            except Exception as e:
                self.log.exception('Error shutting down scheduler')

        self.log.exception('[TERMINATING]')

        # Terminate instance/thread
        sys.exit(0)

    def _check(self) -> None:
        """Checks to decide to populate or sync on startup

        .. danger::
            On errors from the api, calls :py:meth:`_stopper(force=True)` which will terminate thread.
        """

        self.state.set_state(mode='checking', state='running')
        # @TODO: check if in changes/stream - get last, then use last date retrieved as start_date (-1microsecond)
        changes = requests.get('%s?where={"_org_id":%s, "_realm":"%s"}&sort=[("sequence_ordinal", -1)]&max_results=1' %
                               (self.api_integration_url, self.org_id, NIF_REALM),
                               headers=API_HEADERS)

        if changes.status_code == 404:
            # populate, should not happen!
            # self.populate()
            self.log.error('404 from {0}, terminating'.format(self.api_integration_url))
            self._stopper(force=True)

        elif changes.status_code == 200:

            r = changes.json()
            c = r['_items']

            if len(c) == 0:
                self.log.debug('No change records, populating')
                self.populate()

            elif len(c) == 1:
                # Check date then decide to populate or not!
                self.log.debug('Got last change records, checking times')

                sequential_ordinal = dateutil.parser.parse(c[0]['sequence_ordinal']).replace(tzinfo=self.tz_utc)

                self.log.debug('Last change message recorded {0}'.format(sequential_ordinal.astimezone(self.tz_local).isoformat()))

                self.initial_start = sequential_ordinal + timedelta(seconds=self.initial_timedelta) - timedelta(
                    hours=self.overlap_timedelta)

                if self.initial_start.tzinfo is None or self.initial_start.tzinfo.utcoffset(self.initial_start) is None:
                    self.initial_start = self.initial_start.replace(self.tz_local)

                if self.initial_start < datetime.utcnow().replace(tzinfo=self.tz_utc) - timedelta(
                        hours=self.populate_interval):
                    """More than 30 days!"""
                    self.log.debug('More than {} days, populating'.format(self.populate_interval))
                    self.populate()
                    self.state.set_state(mode='populate', state='initialized')
                else:
                    self.log.debug('Less than {} hours, syncing'.format(self.populate_interval))
                    self.job.modify(next_run_time=datetime.now())
                    self.log.debug('Told job to start immediately')
                    self.log.debug('Starting sync scheduler')
                    self.scheduler.start()
                    self.state.set_state(mode='sync', state='started')

        else:
            self.log.error('{0} from {1}, terminating'.format(changes.status_code, self.api_integration_url))
            sys.exit()

    def _eve_fix_sync(self, o) -> dict:
        """Just make soap response simpler

        .. danger::
            Deferred. Uses :py:class:`typings.changes.Changes` instead.
        """

        if o['Changes'] is None:
            o['Changes'] = []
        elif 'ChangeInfo' in o['Changes']:
            o['Changes'] = o['Changes']['ChangeInfo']

            for key, value in enumerate(o['Changes']):
                if o['Changes'][key]['MergeResultOf'] is None:
                    o['Changes'][key]['MergeResultOf'] = []
                elif 'int' in o['Changes'][key]['MergeResultOf']:
                    o['Changes'][key]['MergeResultOf'] = o['Changes'][key]['MergeResultOf']['int']
                else:
                    o['Changes'][key]['MergeResultOf'] = []

        o['_org_id'] = self.org_id

        return o

    def _update_changes(self, changes) -> None:
        """Update change message

        .. note::
            Creates a custom unique '_ordinal' for each change message before trying to insert into api. The purpose
            is to let it gracefully fail with a http 422 if the change message already exists in the api::

                sha224(bytearray(entity_type, id, sequence_ordinal, org_id))

        :param changes: list of change messages
        :type changes: :py:class:`typings.changes.Changes`
        """

        for v in changes:
            v['_ordinal'] = hashlib.sha224(bytearray("%s%s%s%s" % (v['entity_type'],
                                                                   v['id'],
                                                                   v['sequence_ordinal'],
                                                                   self.org_id),
                                                     'utf-8')).hexdigest()
            # bytearray("%s%s%s%s" % (self.org_id, v['EntityType'], v['Id'], v['sequence_ordinal']), 'utf-8')).hexdigest()

            v['_status'] = 'ready'  # ready -> running -> finished
            v['_org_id'] = self.org_id
            v['_realm'] = NIF_REALM

            if 'name' not in v or v['name'] is None:
                v['name'] = 'NA'

            r = requests.post(self.api_integration_url,
                              data=json.dumps(v, cls=EveJSONEncoder),
                              headers=API_HEADERS)

            if r.status_code == 201:
                self.log.debug('Created change message for {0} with id {1}'.format(v['entity_type'],
                                                                                   v['id']))
                self.messages += 1

            elif r.status_code == 422:
                self.log.debug('422 {0} with id {1} already exists error {2}'.format(v['entity_type'],
                                                                                     v['id'], r.text))
            else:
                self.log.error('{0} - Could not create change message for {1} with id {2}'.format(r.status_code,
                                                                                                  v['entity_type'],
                                                                                                  v['id']))
                self.log.error(r.text)

    def _get_change_messages(self, start_date, end_date, resource) -> None:
        """Use NIF GetChanges3"""

        # To avoid future date?
        time.sleep(NIF_SYNC_DELAY)

        if resource == 'changes':
            status, changes = self.nif.get_changes(start_date.astimezone(self.tz_local),
                                                   end_date.astimezone(self.tz_local))
        elif resource == 'payments':
            status, changes = self.nif.get_changes_payments(start_date.astimezone(self.tz_local),
                                                            end_date.astimezone(self.tz_local))
        elif resource == 'competence':
            status, changes = self.nif.get_changes_competence(start_date.astimezone(self.tz_local),
                                                              end_date.astimezone(self.tz_local))
        elif resource == 'license':
            status, changes = self.nif.get_changes_license(start_date.astimezone(self.tz_local),
                                                           end_date.astimezone(self.tz_local))
        elif resource == 'federation':
            status, changes = self.nif.get_changes_federation(start_date.astimezone(self.tz_local),
                                                              end_date.astimezone(self.tz_local))
        else:
            raise Exception('Resource gone bad, {}'.format(resource))

        if status is True:

            self.log.debug('Got {} changes for {}'.format(len(changes), resource))
            if len(changes) > 0:
                self._update_changes(changes)
            else:
                self.log.debug('Empty change messages list')
            """    
            try:
                self.log.debug('Got {} changes for {}'.format(len(changes), resource))
                if len(changes) > 0:
                    self._update_changes(changes)
            except TypeError:
                self.log.debug('Empty change messages list (_get_changes3)')
            except Exception as e:
                self.log.exception('Unknown exception (_get_changes3)')
            """

        else:
            self.log.error('GetChanges returned error: {0} - {1}'.format(changes.get('code', 0),
                                                                         changes.get('error', 'Unknown error')))
            raise Exception('_get_changes_messages returned an error')

    def _get_changes(self, start_date, end_date) -> None:
        """Get change messages based on :py:attr:`.sync_type`"""

        self.from_to = [start_date, end_date]  # Adding extra info

        try:
            self._get_change_messages(start_date, end_date, self.sync_type)

            if self.sync_errors > 0:
                self.sync_errors -= 1

            return True

        except requests.exceptions.ConnectionError:
            self.sync_errors += 1
            self.log.error('Connection error in _get_changes')

            # Retry @TODO see if retry should be in populate and sync
            if NIF_SYNC_MAX_ERRORS >= self.sync_errors:
                time.sleep(3 * self.sync_errors)
                self._get_changes(start_date, end_date)
        except TypeError:
            self.log.debug('TypeError: Empty change messages list ({})'.format(self.sync_type))
        except Exception as e:
            self.sync_errors += 1
            self.log.exception('Exception in _get_changes')
            # @TODO Need to verify if this is reason to warn somehow??

        return False

    def sync(self) -> None:
        """This method is the job run by the scheduler when last change message is < NIF_POPULATE_INTERVAL.

        If a job misfires, then on next run the interval to sync will be twice.

        .. note::
            Checks if :py:attr:`.sync_errors` > :py:attr:`.sync_errors_max` and if so it will set :py:attr:`._stopper`
            for this thread and will run :py:meth:`._stopper` as it always checks, which in turn calls
            :py:meth:`._shutdown` and terminates the thread.
        """

        self.state.set_state(mode='sync', state='running')

        # Check if stopper is set
        self._stopper()

        self.log.debug('Getting sync messages')

        if self.initial_start is not None:
            end = datetime.utcnow().replace(tzinfo=self.tz_utc)
            start = self.initial_start + timedelta(seconds=self.initial_timedelta)

            self.log.debug('From:   {0}'.format(start.astimezone(self.tz_local).isoformat()))
            self.log.debug('To:     {0}'.format(end.astimezone(self.tz_local).isoformat()))

            if end > start:
                if self._get_changes(start, end):
                    self.initial_start = end
            else:
                self.log.error('Inconsistence between dates')
        else:
            end = datetime.utcnow().replace(tzinfo=self.tz_utc)
            self.initial_start = end - timedelta(minutes=self.sync_interval)

            self.log.debug('From:   {0}'.format(self.initial_start.astimezone(self.tz_local).isoformat()))
            self.log.debug('To:     {0}'.format(end.astimezone(self.tz_local).isoformat()))

            if end > self.initial_start:
                if self._get_changes(self.initial_start, end):
                    self.initial_start = end
            else:
                self.log.error('Inconsistence between dates')

        self.state.set_state(mode='sync', state='sleeping')

    def populate(self, sync_after=True) -> None:
        """Populates change messages from :py:attr:`.org_created` until last change message timedelta is less than
        :py:attr:`.populate_interval` from which it will exit and start :py:attr:`scheduler`.

        .. attention::
            :py:meth:`populate` requires a slot in the connectionpool. Getting a slot requires acquiring
            :py:attr:`lock`. Number of slots available is set in :py:mod:`syncdaemon` on startup.
        """
        self.state.set_state(mode='populate', state='initializing')
        self.log.debug('Populate, interval of {0} hours...'.format(self.populate_interval))

        # Initial
        if self.initial_start is None:
            end_date = self.org_created
        else:
            end_date = self.initial_start

        start_date = end_date - timedelta(hours=self.populate_interval)

        # Populate loop
        while end_date < datetime.utcnow().replace(tzinfo=self.tz_utc) + timedelta(hours=self.populate_interval):

            # Check stopper
            self._stopper()

            # Aquire lock and run!
            self.log.debug('Waiting for slot in connectionpool...')
            self.state.set_state(state='waiting', reason='connection pool')

            with self.lock:  # .acquire(blocking=True):
                self.state.set_state(state='running')
                # Check stopper, might have waited long time
                self._stopper()

                # Overlapping end date
                if end_date > datetime.utcnow().replace(tzinfo=self.tz_utc):
                    end_date = datetime.utcnow().replace(tzinfo=self.tz_utc)

                    self.log.debug('Getting last changes between {0} and {1}'
                                   .format(start_date.astimezone(self.tz_local).isoformat(),
                                           end_date.astimezone(self.tz_local).isoformat()))

                    if self._get_changes(start_date, end_date) is True:
                        # Last populate
                        break  # Break while

                else:
                    self.log.debug('Getting changes between {0} and {1}'
                                   .format(start_date.astimezone(self.tz_local).isoformat(),
                                           end_date.astimezone(self.tz_local).isoformat()))

                    if self._get_changes(start_date, end_date) is True:
                        # Next iteration
                        start_date = end_date
                        end_date = end_date + timedelta(hours=self.populate_interval)

                    time.sleep(0.1)  # Grace before we release lock

        # Since last assignment do not work, use last end_date = start_date for last iteration
        self.initial_start = start_date
        self.state.set_state(mode='populate', state='finished', reason='ended populate')

        if sync_after is True:
            self.log.debug('Starting sync scheduler...')
            self.scheduler.start()
            self.state.set_state(mode='sync', state='started', reason='starting after populate')


if __name__ == "__main__":
    print('Running this file directly is not permittet')
    sys.exit(0)

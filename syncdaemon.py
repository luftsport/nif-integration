import Pyro4
from daemon import DaemonContext
from daemon import pidfile
import signal
import argparse
import time
import threading
import sys
import os

from sync import NifSync
from integration import NifIntegration, NifIntegrationUser, NifIntegrationUserError
from organizations import NifOrganization
from settings import (
    NIF_FEDERATION_USERNAME,
    NIF_FEDERATION_PASSWORD,
    NIF_CHANGES_SYNC_INTERVAL,
    NIF_LICENSE_SYNC_INTERVAL,
    NIF_PAYMENTS_SYNC_INTERVAL,
    SYNCDAEMON_PID_FILE,
    SYNC_CONNECTIONPOOL_SIZE,
    NIF_REALM,
    NIF_COMPETENCE_SYNC_INTERVAL,
    RPC_SERVICE_NAME,
    RPC_SERVICE_HOST,
    RPC_SERVICE_PORT,
    NIF_INTEGRATION_GROUPS_AS_CLUBS_MAPPING,
    NIF_INTEGERATION_CLUBS_EXCLUDE,
    NIF_SYNC_TYPES
)
from app_logger import AppLogger

Pyro4.config.COMMTIMEOUT = 10

"""
For integration use
Pyro4.Proxy('PYRO:integration.service@localhost:5555').shutdown()

Pyro4.errors.CommunicationError when not running
"""


@Pyro4.behavior(instance_mode='single')
@Pyro4.expose
class PyroService:
    """A RPC interface based upon Pyro4

    :param workers_stop: The stopper for all worker threads
    :type workers_stop: threading.Event
    :param pyro_stop: The stopper for the RPC interface
    :type pyro_stop: threading.Event
    :param workers_started: A flag for signalling if workers are started
    :type workers_started: threading.Event
    :param daemon: The daemon instance of the RPC interface
    :type daemon: Pyro4.Daemon
    """

    def __init__(self, workers_stop, pyro_stop, workers_started, daemon):
        self.workers_stop = workers_stop
        self.workers_started = workers_started
        self.pyro_stop = pyro_stop
        self.daemon = daemon
        self.work = None
        self.log = AppLogger(name='syncdaemon')
        self.log.info('Pyro service started, ready for commands')
        # self.start_workers()

    def pyro_status(self) -> bool:
        """Returns True as long as RPC is running"""

        return True

    def status(self) -> bool:
        """Returns True as long as RPC is running"""

        return True

    @Pyro4.oneway
    def shutdown(self) -> None:
        """Shutdown. Shutdowns workers then RPC interface and exits daemon context cleanly

        .. attention::
            Since the workers might be asleep awaiting the scheduler event to run the job, this might take
            some time to let all worker threads wake up and then exit cleanly.
        """
        try:
            self.workers_stop.set()
            self.work.shutdown()
        except:
            pass

        try:
            self.pyro_stop.set()
        except:
            pass

    @Pyro4.oneway
    def shutdown_workers(self) -> None:
        """Shutdown all worker threads. See :py:meth:`.shutdown` for notes."""
        if self.work is not None:
            self.work.shutdown()
            self.work = None

    @Pyro4.oneway
    def start_workers(self) -> None:
        """Start all workers"""
        self.workers_stop.clear()
        if self.workers_started.is_set() is False:
            if self.work is None:  # and not isinstance(self.work, SyncWrapper):
                self.work = SyncWrapper(stopper=self.workers_stop, workers_started=self.workers_started, restart=True)

            self.work.start()

    @Pyro4.oneway
    def reboot_workers(self) -> None:
        """Reboot all workers. Shuts down all workers before startup. See :py:meth:`.shutdown` for notes."""
        self.workers_stop.set()
        try:
            self.shutdown_workers()
            time.sleep(0.5)
            self.start_workers()

        except Exception as e:
            self.log.exception('Exception restarting workers', e)
            pass

    def get_workers_status(self) -> [dict]:
        """Get status of all worker threads. Indexed according to :py:attr:`.work.workers`"""
        status = []
        for index, worker in enumerate(self.work.workers):
            status.append(self.get_worker_status(index))
        return status

    def get_worker_status(self, index) -> dict:
        """Returns status of worker at index in :py:attr:`.work.workers`

        :param index: Worker index, starts at 0
        :type index: int
        """
        return {'name': self.work.workers[index].name,
                'id': self.work.workers[index].id,
                'status': self.work.workers[index].is_alive(),
                'state': self.work.workers[index].state.get_state().get('state', 'error'),
                'mode': self.work.workers[index].state.get_state().get('mode', 'Unknown'),
                'reason': self.work.workers[index].state.get_state().get('reason', 'Unknown'),
                'index': index,
                'uptime': self.work.workers[index].uptime,
                'started': self.work.workers[index].started,
                'messages': self.work.workers[index].messages,
                'sync_type': self.work.workers[index].sync_type,
                'sync_interval': self.work.workers[index].from_to,
                'sync_misfires': self.work.workers[index].job_misfires,
                'sync_errors': self.work.workers[index].sync_errors,
                'next_run_time': self.work.workers[index].job_next_run_time
                }

    def restart_worker(self, index) -> bool:
        """Restart worker at index in :py:attr:`.work.workers`

        .. attention::
            Will only try to start a dead worker, it will not shutdown and then start the worker

        :param index: Worker index, starts at 0
        :type index: int
        """

        if self.work.workers[index].is_alive() is False:
            self.work.workers[index].run()  # start()

        return self.work.workers[index].is_alive()

    def get_logs(self) -> [dict]:
        """Get the logs retained by the logger for all :py:attr:`.work.workers`"""

        log = []
        for w in self.get_workers_status():
            log.append({'id': w['id'], 'log': self.get_worker_log(w['index'])})

        return log

    def get_worker_log(self, index) -> dict:
        """Get retained log from worker at index in :py:attr:`.work.workers`

        :param index: Worker index, starts at 0
        :type index: int
        """
        return self.work.workers[index].log.get_tail()

    def get_failed_clubs(self) -> list:
        """Get clubs that failed startup"""

        return self.work.failed_clubs


class PyroWrapper(threading.Thread):
    def __init__(self, workers_stop, pyro_stop, workers_started):  # , work):
        super().__init__(name='pyro-object')

        self.pyro_stop = pyro_stop
        self.workers_stop = workers_stop
        self.workers_started = workers_started

        self.log = AppLogger(name='syncdaemon')

    def loop_cond(self):
        return not self.pyro_stop.is_set()

    def run(self):
        daemon = Pyro4.Daemon(host=RPC_SERVICE_HOST,
                              port=RPC_SERVICE_PORT)

        pw = PyroService(workers_stop=self.workers_stop,
                         pyro_stop=self.pyro_stop,
                         workers_started=self.workers_started,
                         daemon=daemon)

        uri = daemon.register(pw, objectId=RPC_SERVICE_NAME)

        daemon.requestLoop(loopCondition=self.loop_cond)
        self.log.warning('Pyro wrapper shutdown')
        daemon.close()


class SyncWrapper:
    def __init__(self, stopper, workers_started, restart=False):

        self.log = AppLogger(name='syncdaemon')

        self.workers = []
        self.failed_clubs = []
        self.stopper = stopper
        self.workers_started = workers_started
        self.club_list = []

        self.integration = NifIntegration()
        self.bound_semaphore = threading.BoundedSemaphore(value=SYNC_CONNECTIONPOOL_SIZE)

        self.restart = restart

        # Build list of workers
        # for i in range(0, 10):
        #    self.workers.append(ProducerThread(i, workers_stop, restart))

        # time.sleep(1)

    def start(self, start=False):

        self.log.info('Starting workers')
        self.workers_started.set()


        if 'changes' in NIF_SYNC_TYPES:
            integration_users = []

            # clubs = self.integration.get_clubs()

            # Only a list of integers! NIF Clubs
            clubs = self.integration.get_active_clubs(type_id=5)

            self.log.info('Got {} integration users'.format(len(clubs)))

            # Setup each integration user from list of integers
            for club_id in clubs:

                if club_id in self.club_list:
                    continue
                elif club_id not in NIF_INTEGERATION_CLUBS_EXCLUDE:
                    self.club_list.append(club_id)
                elif club_id in NIF_INTEGERATION_CLUBS_EXCLUDE:
                    self.club_list.append(NIF_INTEGRATION_GROUPS_AS_CLUBS_MAPPING[club_id])

                try:
                    if club_id not in NIF_INTEGERATION_CLUBS_EXCLUDE:
                        integration_users.append(NifIntegrationUser(club_id=club_id,
                                                                    create_delay=0))
                        time.sleep(0.2)

                except NifIntegrationUserError as e:
                    self.log.exception('Problems creating user for club_id {}: {}'.format(club_id, e))
                    self.failed_clubs.append({'name': 'From list', 'club_id': club_id})
                except Exception as e:
                    self.log.exception('Problems with club id {}: {}'.format(club_id, e))
                    self.failed_clubs.append({'name': 'From list', 'club_id': club_id})

            # Sleep because last created user!
            time.sleep(140)
            # Add each integration user to workers
            for club_user in integration_users:

                try:

                    if club_user.test_login():

                        # CHANGES: Persons, Functions, Organizations
                        if 'changes' in NIF_SYNC_TYPES:
                            self.workers.append(NifSync(org_id=club_user.club_id,
                                                        username=club_user.username,
                                                        password=club_user.password,
                                                        created=club_user.club_created,
                                                        stopper=self.stopper,
                                                        restart=self.restart,
                                                        background=False,
                                                        initial_timedelta=0,
                                                        overlap_timedelta=5,
                                                        lock=self.bound_semaphore,
                                                        sync_type='changes',
                                                        sync_interval=NIF_CHANGES_SYNC_INTERVAL))

                            self.log.info('Added CHANGES {}'.format(club_user.username))



                    else:
                        self.log.error('Failed login for {} with password {}'.format(club_user.club_id, club_user.password))
                        self.failed_clubs.append({'name': club_user.club_name, 'club_id': club_user.club_id})

                except Exception as e:
                    self.failed_clubs.append({'name': club_user.club_name, 'club_id': club_user.club_id})
                    self.log.exception('Problems for {} ({})'.format(club_user.club_name, club_user.club_id))



        # Add license-sync
        try:
            self.log.info('Adding competences and license sync')
            org = NifOrganization(376)

            if 'payments' in NIF_SYNC_TYPES:
                # CHANGES: Payments
                time.sleep(1)
                self.workers.append(NifSync(org_id=900003,
                                            username=NIF_FEDERATION_USERNAME,
                                            password=NIF_FEDERATION_PASSWORD,
                                            created='2019-10-01T00:00:00Z', #org.created,
                                            stopper=self.stopper,
                                            restart=self.restart,
                                            background=False,
                                            initial_timedelta=0,
                                            overlap_timedelta=5,
                                            lock=self.bound_semaphore,
                                            sync_type='payments',
                                            sync_interval=NIF_PAYMENTS_SYNC_INTERVAL))


            if 'license' in NIF_SYNC_TYPES:
                self.workers.append(NifSync(org_id=900001,
                                            username=NIF_FEDERATION_USERNAME,
                                            password=NIF_FEDERATION_PASSWORD,
                                            created=org.created,
                                            stopper=self.stopper,
                                            restart=self.restart,
                                            background=False,
                                            initial_timedelta=0,
                                            overlap_timedelta=5,
                                            lock=self.bound_semaphore,
                                            sync_type='license',
                                            sync_interval=NIF_LICENSE_SYNC_INTERVAL))

            if 'competence' in NIF_SYNC_TYPES:
                self.workers.append(NifSync(org_id=900002,
                                            username=NIF_FEDERATION_USERNAME,
                                            password=NIF_FEDERATION_PASSWORD,
                                            created=org.created,
                                            stopper=self.stopper,
                                            restart=self.restart,
                                            background=False,
                                            initial_timedelta=0,
                                            overlap_timedelta=5,
                                            lock=self.bound_semaphore,
                                            sync_type='competence',
                                            sync_interval=NIF_COMPETENCE_SYNC_INTERVAL))

            if 'federation' in NIF_SYNC_TYPES:
                self.workers.append(NifSync(org_id=376,
                                            username=NIF_FEDERATION_USERNAME,
                                            password=NIF_FEDERATION_PASSWORD,
                                            created=org.created,
                                            stopper=self.stopper,
                                            restart=self.restart,
                                            background=False,
                                            initial_timedelta=0,
                                            overlap_timedelta=5,
                                            lock=self.bound_semaphore,
                                            sync_type='federation',
                                            sync_interval=NIF_COMPETENCE_SYNC_INTERVAL))
        except Exception as e:
            self.log.exception('Error initiating licenses and competences')

        # Start all workers
        self.log.info('Starting all workers')
        for worker in self.workers:
            worker.start()
            time.sleep(1)  # Spread each worker accordingly

    def shutdown(self):
        self.log.info('Shutdown workers called')
        self.stopper.set()
        for worker in self.workers:
            self.log.info('Joining {}'.format(worker.name))
            worker.join()
        self.workers_started.clear()


# Stoppers
workers_stop = threading.Event()
pyro_stop = threading.Event()
workers_started = threading.Event()


# Globals for signals
def shutdown_workers(signum, frame):
    """Sets the stopper threading event
    Shuts down all workers including pyro rpc interface
    """
    workers_stop.set()
    # pyro_stop.set()


def reboot_workers(signum, frame):
    """Sets the restart threading event
    Shuts down all workers, then restarts them"""


# Signal maps to function living in global ex SIGKILL
signal_map = {
    signal.SIGHUP: shutdown_workers,
    signal.SIGINT: shutdown_workers,
    signal.SIGTTIN: shutdown_workers,
    signal.SIGTTOU: shutdown_workers,
    signal.SIGTERM: shutdown_workers,
    signal.SIGTSTP: shutdown_workers,
    signal.SIGUSR1: reboot_workers,
}

if __name__ == '__main__':
    log = AppLogger(name='syncdaemon')

    log.info('[STARTUP]')
    log.info('** ENV: {} **'.format(NIF_REALM))
    log.info('Entering daemon context')
    with DaemonContext(signal_map=signal_map,
                       detach_process=True,  # False for running front
                       stdin=None,
                       stdout=None,  # sys.stdout,  # None
                       stderr=None,  # sys.stderr,  # None
                       pidfile=pidfile.PIDLockFile(
                           '{}/{}'.format(os.getcwd(), SYNCDAEMON_PID_FILE)),
                       chroot_directory=None,  # Same
                       working_directory='{}/'.format(os.getcwd())
                       ):

        pyro = PyroWrapper(workers_stop=workers_stop,
                           pyro_stop=pyro_stop,
                           workers_started=workers_started
                           )
        pyro.start()

        # Main loop
        while not pyro_stop.is_set():
            # Housecleaning?
            time.sleep(5)

        # Pyro4.Daemon.shutdown()
        # Join all workers!

        pyro.join()

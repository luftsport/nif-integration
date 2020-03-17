from daemon import DaemonContext
from daemon import pidfile
import signal
import argparse
import time
import threading
import sys
import os
from stream import NifStream
from app_logger import AppLogger
from settings import STREAMDAEMON_PID_FILE

# Stoppers
workers_stop = threading.Event()


# Globals for signals
def shutdown_workers(signum, frame):
    """Sets the stopper threading event
    @TODO see if RPC is needed
    """
    workers_stop.set()
    sys.exit(0)


# Signal maps to function living in global ex SIGKILL
signal_map = {
    signal.SIGHUP: shutdown_workers,
    signal.SIGINT: shutdown_workers,
    signal.SIGTTIN: shutdown_workers,
    signal.SIGTTOU: shutdown_workers,
    signal.SIGTERM: shutdown_workers,
    signal.SIGTSTP: shutdown_workers,
    # signal.SIGUSR1: reboot_workers,
}

if __name__ == '__main__':
    log = AppLogger(name='streamdaemon')

    log.info('[STARTUP]')
    log.info('Entering daemon context')
    with DaemonContext(signal_map=signal_map,
                       detach_process=True,  # False for running front
                       stdin=None,
                       stdout=sys.stdout,  # None
                       stderr=sys.stderr,  # None
                       pidfile=pidfile.PIDLockFile(
                           '{}/{}'.format(os.getcwd(), STREAMDAEMON_PID_FILE)),
                       chroot_directory=None,  # Same
                       working_directory='{}/'.format(os.getcwd())
                       ):

        stream = NifStream()
        log.info('Running stream run')
        try:
            stream.run()
        except:
            log.exception('Error in stream.run')

        # Cleanup before exiting?
        try:
            log.info('Running recover')
            stream.recover(errors=False)

        except:
            log.exception('Error running recover')

        log.info('Exiting daemon context')

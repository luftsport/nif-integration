from daemon import DaemonContext
from daemon import pidfile
import signal
import time
import sys
import os
from stream import NifStream
from app_logger import AppLogger
from settings import STREAMFIX_PID_FILE


def shutdown(signum, frame):
    log.info('[SHUTDOWN]')
    sys.exit(0)


# Signal maps to function living in global ex SIGKILL
signal_map = {
    signal.SIGHUP: shutdown,
    signal.SIGINT: shutdown,
    signal.SIGTTIN: shutdown,
    signal.SIGTTOU: shutdown,
    signal.SIGTERM: shutdown,
    signal.SIGTSTP: shutdown,
    signal.SIGUSR1: shutdown,
}

if __name__ == '__main__':
    log = AppLogger(name='streamfixdaemon')

    log.info('[STARTUP]')
    log.info('Entering daemon context')
    with DaemonContext(signal_map=signal_map,
                       detach_process=True,  # False for running front
                       stdin=None,
                       stdout=sys.stdout,  # None
                       stderr=sys.stderr,  # None
                       pidfile=pidfile.PIDLockFile(
                           '{}/{}'.format(os.getcwd(), STREAMFIX_PID_FILE)),
                       chroot_directory=None,  # Same
                       working_directory='{}/'.format(os.getcwd())
                       ):

        stream = NifStream()
        time.sleep(1)
        log.info('RECOVERY start errors False')
        stream.recover(errors=False)
        time.sleep(1)
        log.info('RECOVERY start errors True')
        stream.recover(errors=True)
        log.info('[FINISHED] all done fixing')
        log.info('Exiting daemon context')

import logging
from collections import deque


class TailLogHandler(logging.Handler):
    def __init__(self, maxlen, *args, **kwargs):
        logging.Handler.__init__(self, *args, **kwargs)
        self.log_queue = deque(maxlen=maxlen)  # log_queue

    def emit(self, record):
        self.log_queue.append(self.format(record))

    def last(self):
        return list(self.log_queue)

    def close(self):
        logging.Handler.close(self)


class AppLogger:
    """Simple logging wrapper for applications
    Creates a logger and corresponding file (<name>.log) on the given name"""

    def __init__(self, name, path='logs', stdout=True, last_logs=0, restart=True):

        # create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # create formatter
        # formatter = logging.Formatter('[%(asctime)s] - %(name)s - %(levelname)s - %(message)s')


        # Reset all handlers if restart
        if restart is True:
            self.logger.handlers = []

        if not len(self.logger.handlers):

            fh = logging.FileHandler('{}/{0}.log'.format(path, name))
            fh_formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(fh_formatter)
            self.logger.addHandler(fh)

            self.tailer = TailLogHandler(last_logs)
            tailer_formatter = logging.Formatter('%(asctime)s|%(levelname)s|%(message)s')
            self.tailer.setLevel(logging.ERROR)
            self.tailer.setFormatter(tailer_formatter)
            self.logger.addHandler(self.tailer)

            if stdout:
                ch = logging.StreamHandler()
                ch.setFormatter(fh_formatter)
                ch.setLevel(logging.DEBUG)
                self.logger.addHandler(ch)

    def debug(self, msg):
        self.logger.debug(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def critical(self, msg):
        self.logger.critical(msg)

    def exception(self, msg):
        """Always exc_info=True"""
        self.logger.exception(msg)

    def get_tail(self):
        return self.tailer.last()

""" Simple logging for Vintage.Next development. """

import sublime

import os

_package_dir = os.path.join(sublime.packages_path(), 'Vintage.Next')
_log_file = os.path.join(_package_dir, 'log.log')

QUIET = 0
INFO = 1
WARNING = 2
DEBUG = 3


def delete_log_maybe():
    data = os.lstat(_log_file)
    if data["st_size"] / 1024 > (1024 * 1024):
        os.unlink(_log_file)

class Logger(object):

    def __init__(self, level=INFO, prefix=""):
        self.prefix = prefix
        self.level = level
        # TODO: delete if it gets too big.
        self.out = open(_log_file, 'a')

    def info(self, msg):
        if self.level >= INFO:
            self.out.write("INFO: %s%s\n" % (self.prefix, msg))
            self.out.flush()

    def debug(self, msg):
        if self.level >= DEBUG:
            self.out.write("DEBUG: %s%s\n" % (self.prefix, msg))
            self.out.flush()

    def warn(self, msg):
        if self.level >= WARNING:
            self.out.write("WARNING: %s%s\n" % (self.prefix, msg))
            self.out.flush()

    def empty(self):
        data = os.lstat(_log_file)
        if data.st_size / 1024 <= (1024 * 1024):
            return

        self.out.close()
        self.out = open(_log_file, "w")
        self.out.write("")
        self.out.close()
        self.out = open(_log_file, "a")

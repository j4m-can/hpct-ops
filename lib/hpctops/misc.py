# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# hpctops/misc/__init__.py


"""Collection of miscellaneous objects.
"""


import functools
import inspect
import logging
import secrets
import time


_app_logger = logging.getLogger(__name__)


def get_methodname(self):
    """Return method name of caller."""

    fname = inspect.stack()[1].function
    return f"{self.__class__.__name__}.{fname}"


def get_nonce():
    """Return a nonce."""

    return secrets.token_urlsafe()


def get_timestamp():
    """Return a timestamp (string)."""

    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def log_enter_exit(msg=None, logfn=None):
    """Decorator factory to report enter and exit messages via log
    function.

    Args:
        msg: Message to show in log entry.
        logfn: Alternate function to log message. Default is to
            logger.debug of the application logger.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                qualname = getattr(func, "__qualname__", "na")
                _msg = msg or f"[{qualname}]"
                _logfn = logfn or _app_logger.debug

                try:
                    tenter = time.time()
                    _logfn(f"{_msg} ENTER [tenter={tenter}]")
                except:
                    pass

                return func(*args, **kwargs)
            finally:
                try:
                    texit = time.time()
                    telapsed = texit - tenter
                    _logfn(f"{_msg} EXIT [texit={texit}] [telapsed={telapsed}]")
                except:
                    pass

        return wrapper

    return decorator


def service_forced_update(what=None):
    """Decorator factory to wrap a function call in try-finally and
    ensure that Charm.service_set_updated() and
    Charm.service_update_status() are called.

    Args:
        what: Corresponds to the Charm.service_set_updated() what argument
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                qualname = getattr(func, "__qualname__", "na")
                # TODO: tweak this to trim qualname if necessary
                _what = what or f"[{qualname}]"
                self = args[0] if args else None
                # cls = getattr(self, "__class__")
                # verify cls is subclass of CharmBase!

                return func(*args, **kwargs)
            finally:
                try:
                    if self and hasattr(self, "service_set_updated"):
                        # assume a ServiceCharm
                        self.service_set_updated(_what)
                        self.service_update_status()
                except:
                    pass

        return wrapper

    return decorator

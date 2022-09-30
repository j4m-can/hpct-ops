# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# hpctops/charm/debugger.py


"""Special operator debugging.

Before defining the local operator, do one of the following:

1) If using CharmBase:
    # interpose DebuggerCharm
    import ops.charm
    from hpctops.charm.debugger import DebuggerCharm as CharmBase

2) If using something other than CharmBase, e.g., ServiceCharm:
    # interpose DebuggerCharm
    from hpctops.charm import set_base_charm
    set_base_charm(ServiceCharm)
    from hpctops.charm.debugger import DebuggerCharm as ServiceCharm

Update charm yaml files from the hpctops/share/hpctops/DebuggerCharm):
1) add contents of share/hpctops/DebuggerCharm/action.yaml to action.yaml
2) add contents of share/hpctops/DebuggerCharm/config.yaml to config.yaml
"""


import base64
from doctest import OutputChecker
import logging
import socket
import time
import types

from ops.charm import ActionMeta, ActionEvent, CharmBase, CharmEvents
from ops.framework import StoredState

from hpctops.misc import get_methodname, log_enter_exit


logger = logging.getLogger(__name__)


def canonicalize(value):
    """Convert to conform to restricted key names.

    See (2022-06-30):
        _ACTION_RESULT_KEY_REGEX = re.compile(r'^a-z0-9?$')" in ops.model.
    """

    if type(value) == dict:
        _value = {}
        for k, v in value.items():
            k = k.replace("_", "-")
            _value[k] = canonicalize(v)
    elif type(value) in [list, set]:
        _value = []
        for v in value:
            _value.append(canonicalize(v))
        if type(value) == set:
            _value = set(_value)
    else:
        v = value
    return v


def get_object_by_name(self, event, name):
    """Get object by resolving name components.

    Only self and event are supported.
    """

    if (
        name not in ["self", "event"]
        and not name.startswith("self.")
        and not name.startswith("event.")
    ):
        msg = "name must be self.<...> or event.<...>"
        event.log(msg)
        raise Exception("name must be self.<...> or event.<...>")

    comps = name.split(".")
    if comps[0] == "self":
        o = self
    elif comps[0] == "event":
        o = event
    for comp in comps[1:]:
        o = getattr(o, comp)
        if o == None:
            msg = f"bad reference ({comp}) in name ({name})"
            event.log(msg)
            raise Exception(msg)
    return o


def event2json(event):
    """Extract event info."""

    return {
        "kind": event.event_kind,
        "type": event.event_type,
    }


def stringify(value):
    """Convert object references to string values.

    Note: This is not lossless if references do not convert to unique
    string values.
    """

    if type(value) == dict:
        _value = {}
        for k, v in value.items():
            _value[stringify(k)] = stringify(v)
    elif type(value) in [list, set]:
        _value = []
        for v in value:
            _value.append(stringify(v))
        if type(value) == set:
            _value = set(_value)
    elif type(value) == str:
        _value = value
    else:
        # stringify (cannot send reference)
        # ensure uniqueness with id()
        _value = f"{hex(id(value))} {str(value)}"
    return _value


def unit2json(unit):
    """Extract unit info."""

    return {
        "app": unit.app,
        "is_leader": unit.is_leader(),
        "name": unit.name,
        "status": unit.status,
    }


def set_charmbase(charmbase):
    """Helper to set the charmbase class that the DebuggerCharm will
    be created with.
    """
    global DebuggerCharmBase

    DebuggerCharmBase = charmbase
    return DebuggerCharm


class DebuggerCharmBase(CharmBase):
    pass


class DebuggerCharm(DebuggerCharmBase):
    """Provides default actions useful for debugging, and intercepts
    all registered observed events.
    """

    def __init__(self, *args, **kwargs):
        self.debugger_handlers = {}

        # initialize base charm
        super().__init__(*args, **kwargs)

        config = self.config

        # set up debugger action handlers
        for name in self.framework.meta.actions:
            if name.startswith("debugger-"):
                name = name.replace("-", "_")
                self.framework.observe(
                    getattr(self.on, f"{name}_action"), getattr(self, f"_on_{name}_action")
                )

        # substitute observe method if intercepting
        if config.get("debugger-intercept-handler"):
            self._framework_observe = self.framework.observe
            self.framework.observe = self._observe

    @log_enter_exit()
    def _debugger_out(self, event, value, encoding=None, output=None):
        """Create output object and write to particular destination.

        Args:
            event: Event being handled.
            value: Value to be encapsulated into output.
            encoding: Encoding to use for output: base64, canonical,
                string. Default is in ```params["encoding"]```.
            output: Destination for output: debug-log, event-log,
                event-result. Default is in ```params["output"]```.
        """

        h = "_debugger_out"

        if not encoding:
            if hasattr(event, "params"):
                encoding = event.params.get("encoding")
            if not encoding:
                encoding = "string"
        if not output:
            if hasattr(event, "params"):
                output = event.params.get("output")
            if not output:
                output = "debug-log"

        # convert (non-portable) object references to strings
        value = stringify(value)

        # convert value to desired encoding
        if encoding == "base64":
            value = str(base64.b64encode(bytes(value, encoding="utf-8")), encoding="utf-8")
        elif encoding == "canonical":
            value = canonicalize(value)
        elif encoding == "string":
            value = str(value)

        # package result
        result = {
            "h": f"{h}",
            "event": f"{event}",
            "unit": f"{self.unit}",
            "encoding": f"{encoding}",
            "value": value,
        }

        if output == "debug-log":
            logger.debug(f"[{h}] result ({result})")
        elif output == "event-log":
            event.log(f"[{h}] result ({result})")
        elif output == "event-result":
            event.set_results(result)

    def _observe(self, event, handler):
        """Alternate ```observe()```. Intercepts the request to
        register a handler and instead registers a debugger handler.
        When triggered, the debugger handler will call the original
        handler.
        """

        eventkind = event.event_kind
        self.debugger_handlers[eventkind] = handler

        logger.debug(
            f"[{get_methodname(self)}] register for event ({event}) eventkind ({eventkind}) handler ({handler})"
        )
        self._framework_observe(event, self._on_debugger_intercept_handler)

    @log_enter_exit()
    def _on_debugger_execute_action(self, event):
        """Execute code snippet.

        Anything available within the context of this handler can be
        referenced.
        """

        code = event.params["code"]
        value_type = event.params["value-type"]

        try:
            from io import StringIO
            from contextlib import redirect_stdout

            f = StringIO()
            with redirect_stdout(f):
                try:
                    exec(code)
                    out = f.getvalue()
                    err = None
                except Exception as e:
                    err = f"{e}"
                    out = None
        except Exception as e:
            event.log(f"{e}")

        if value_type == "full":
            value = {
                "output": out,
                "error": err,
            }
        elif value_type == "output":
            value = out
        elif value_type == "error":
            value = err

        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_dirof_action(self, event):
        """Run ```dir()``` on identifier in name."""

        try:
            name = event.params["name"]
            o = get_object_by_name(self, event, name)
            value = dir(o)
        except Exception as e:
            event.log(e)
            raise

        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_event_action(self, event):
        """Dump event action in somewhat detailed way.

        Note: The event passed to this method is of limited use, but
        is helpful for instruction and minor testing.
        """

        value = event2json(event)
        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_handlers_action(self, event):
        """Dump a list a handlers registered for observation."""

        bad_hnames = ["define_event", "events", "framework", "model", "handle", "handle_kind"]

        hnames = [
            hname
            for hname in dir(self.on)
            if not hname.startswith("_") and hname not in bad_hnames
        ]
        value = {hname: getattr(self.on, hname) for hname in sorted(hnames)}
        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_host_action(self, event):
        """Dump hostname."""

        value = socket.gethostname()
        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_object_action(self, event):
        """Dump arbitrary object which must be accessible from within
        this method.
        """

        try:
            name = event.params["name"]
            o = get_object_by_name(self, event, name)
            value = o
        except Exception as e:
            event.log(e)
            raise

        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_stored_action(self, event):
        """Dump the ```_stored``` object, if present."""

        if hasattr(self, "_stored"):
            value = self._stored._data._cache
            self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_time_action(self, event):
        """Dump the ```time.time()``` value."""

        value = f"{time.time()}"
        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_typeof_action(self, event):
        """Dump type information for an arbitrary object which is
        accessible from this method.
        """

        try:
            name = event.params["name"]
            o = get_object_by_name(self, event, name)
            value = type(o)
        except Exception as e:
            event.log(e)
            raise

        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_dump_unit_action(self, event):
        """Dump unit information in somewhat detailed way."""

        value = unit2json(self.unit)
        self._debugger_out(event, value)

    @log_enter_exit()
    def _on_debugger_intercept_handler(self, event):
        """Generic untercept handler for all non-debugger handlers.

        The next handler to be called, as registered with
        ```observe()```, is found in ```self.debugger_handlers```, and
        called with the received ```event```.
        """

        eventkind = event.handle.kind
        h = f"[debugger-intercept [{eventkind}]]"

        logger.debug(f"{h} PRE")
        # add code here to enhance debugging

        handler = self.debugger_handlers[eventkind]
        logger.debug(f"{h} event ({event}) HANDLER ({handler})")
        handler(event)

        logger.debug(f"{h} POST")
        # add code here to enhance debugging

    @log_enter_exit()
    def _on_debugger_trigger_update_status_action(self, event):
        """Trigger ```update-status``` (if named
        ```_on_update_status```).
        """

        try:
            value = None
            handler = self.debugger_handlers.get("update_status")
            if handler:
                handler(event)
        except Exception as e:
            value = e
        self._debugger_out(event, value)

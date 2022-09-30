# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# hpctops/charm/service.py


"""Provides the ServiceCharm class which serves as the starting point
for service charms that offer common service-oriented functionality.
"""


import logging
from typing import Union

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from ..misc import get_methodname, get_timestamp, log_enter_exit, service_forced_update


logger = logging.getLogger(__name__)


PRESTARTED_STATES = [
    "enabled",
    "waiting",
    "broken",
]

STARTED_STATES = [
    "started",
    "waiting",
    "broken",
]


class ServiceCharmException(Exception):
    pass


class ServiceCharm(CharmBase):
    """Provide support for managing service(s).

    Handlers:
        config-changed, install, start, stop, update-status

    Actions (see actions.yaml):
        restart, start, stop, sync

    State:
        service_stale - (boolean) true is config is stale
        service_state - (string) one of: idle, enabled, started
        service_syncs - (dict) map of sync key and boolean
        service_updated - (string) timestamp of last config update
    """

    _service_stored = StoredState()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._service_required_syncs = []
        self._service_sync_handlers = {}

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.update_status, self._on_update_status)

        self.framework.observe(self.on.service_restart_action, self._on_service_restart_action)
        self.framework.observe(self.on.service_set_sync_action, self._on_service_set_sync_action)
        self.framework.observe(self.on.service_start_action, self._on_service_start_action)
        self.framework.observe(self.on.service_stop_action, self._on_service_stop_action)
        self.framework.observe(self.on.service_sync_action, self._on_service_sync_action)

        # update these using get/set
        self._service_stored.set_default(
            stale=True,
            state="idle",
            status_message=None,
            syncs={},
            updated=None,
        )

        # update here, at least; hopefully in a later method, too
        self.service_set_updated("init")

    #
    # registered handlers
    #
    # Note: These methods should *not* be called directly.
    #

    @log_enter_exit()
    @service_forced_update("config-changed")
    def _on_config_changed(self, event):
        """'on-config-changed' handler.

        Note: Do not override.
        """

        self._service_on_config_changed(event)

    @log_enter_exit()
    def _on_install(self, event):
        """'install' handler.

        Note: Do not override.
        """

        self.service_install(event)

    @log_enter_exit()
    def _on_start(self, event):
        """'start' handler.

        Note: Do not override.
        """

        self.service_enable(event)
        self.service_start(event)

    @log_enter_exit()
    def _on_stop(self, event):
        """'stop' handler.

        Note: Do not override.
        """

        self.service_stop(event)
        self.service_disable(event)
        self.service_update_status()

    @log_enter_exit()
    def _on_update_status(self, event):
        """'update-status' handler.

        Note: Do not override.
        """
        self.service_update_status()

    #
    # service-specific
    #

    @log_enter_exit()
    @service_forced_update("restart-action")
    def _on_service_restart_action(self, event):
        """'service-restart' action handler.

        Note: Do not override.
        """

        try:
            force = event.params["force"]
            sync = event.params["sync"]
        except:
            force = False
            sync = False

        self.service_restart(force, sync)

    @log_enter_exit()
    def _on_service_set_sync_action(self, event):
        """'service-set-sync-status' action handler.

        Note: Do not override.
        """

        try:
            key = event.params["key"]
            status = event.params["status"]

            if self.service_get_sync(key) != None:
                self.service_set_sync(key, status)
                self.service_update_status()
        except Exception as e:
            logger.debug(f"[{get_methodname(self)} e ({e})")

    @log_enter_exit()
    def _on_service_start_action(self, event):
        """'service-start' action handler.

        Note: Do not override.
        """

        self.service_start(event)

    @log_enter_exit()
    def _on_service_stop_action(self, event):
        """'service-stop' action handler.

        Note: Do not override.
        """

        try:
            force = event.params["force"]
        except:
            force = False

        self.service_stop(event, force)

    @log_enter_exit()
    @service_forced_update("sync-action")
    def _on_service_sync_action(self, event):
        """'service-sync' action handler.

        Note: Do not override.
        """

        try:
            force = event.params["force"]
        except:
            force = False

        self.service_sync(event, force)

    #
    # May be overriden
    #
    # Note: These methods should *not* be called directly. Instead,
    #   call the service_* methods.
    #

    @log_enter_exit()
    def _service_disable(self, event, force):
        """Disable service.

        Called by service_disable().
        """

        pass

    @log_enter_exit()
    def _service_enable(self, event, force):
        """Enable service.

        Called by service_enable.
        """

        pass

    @log_enter_exit()
    def _service_on_config_changed(self, event):
        """Handle config-change event.

        Called by _on_config_changed.
        """

        pass

    @log_enter_exit()
    def _service_install(self, event):
        """Install.

        Called by service_install().
        """

        pass

    @log_enter_exit()
    def _service_start(self, event):
        """Start service.

        Called by service_start().
        """

        pass

    @log_enter_exit()
    def _service_stop(self, event, force):
        """Stop service.

        Called by service_stop().
        """

        pass

    @log_enter_exit()
    def _service_sync(self, event, force=False):
        """Sync all.

        Called by service_sync().
        """

        pass

    #
    # public (do not override)
    #

    @log_enter_exit()
    @service_forced_update("disable")
    def service_disable(self, event, force=False):
        """Disable service(s).

        Note: Do not override.
        """

        if self.service_get_state() == "enabled":
            try:
                self._service_disable(event, force)
                self.service_set_state("idle")
                self.service_set_updated("disable")
            except Exception as e:
                logger.debug(f"[{get_methodname(self)} e ({e})")

    @log_enter_exit()
    @service_forced_update("enable")
    def service_enable(self, event, force=False):
        """Enable service(s).

        Note: Do not override.
        """

        if self.service_get_state() == "idle":
            try:
                self._service_enable(event, force)
                self.service_set_state("enabled")
                self.service_set_updated("enable")
            except Exception as e:
                logger.debug(f"[{get_methodname(self)} e ({e})")

    @log_enter_exit()
    def service_get_syncs(self):
        """Return service syncs object.

        Note: Do not override.
        """

        return dict(self._service_stored.syncs)

    @log_enter_exit()
    def service_get_sync(self, key):
        """Return service sync status for key.

        Should use objects.

        Note: Do not override.
        """

        return self._service_stored.syncs.get(key, False)

    @log_enter_exit()
    def service_get_stale(self):
        """Get service stale state.

        Note: Do not override.
        """

        return self._service_stored.stale

    @log_enter_exit()
    def service_get_state(self):
        """Get service state.

        Note: Do not override.
        """

        return self._service_stored.state

    @log_enter_exit()
    def service_get_updated(self):
        """Return service updated timestamp.

        Note: Do not override.
        """

        return self._service_stored.updated

    @log_enter_exit()
    def service_init_sync(self, key, status: bool, handler=None):
        """Initialize sync status for key that does not yet exist.

        Note: Do not override.
        """

        if key not in self._service_stored.syncs:
            self.service_set_sync(key, status)
        self._service_sync_handlers[key] = handler

    @log_enter_exit()
    @service_forced_update("install")
    def service_install(self, event):
        """Install.

        Note: Do not override.
        """

        self._service_install(event)

    @log_enter_exit()
    def service_is_running(self):
        """Return if service is actually running.

        By default, this is dependent on the state being "started",
        but can be different.

        Note: Do not override.
        """

        return self.service_get_state() in ["started", "waiting", "broken"]

    @log_enter_exit()
    def service_is_synced(self):
        """Return True if all "requires" are synced.

        Note: Do not override.
        """

        for name in self._service_required_syncs:
            if not self.service_get_sync(name):
                return False
        return True

    @log_enter_exit()
    def service_restart(self, event, force=False, sync=False):
        """Restart service(s).

        Note: Do not override.
        """

        self.service_stop(event, force)
        self.service_start(event)
        # self.service_set_updated("reinstall")

    @log_enter_exit()
    def service_set_required_syncs(self, keys):
        """Set list of required syncs.

        Note: Do not override."""

        self._service_required_syncs = keys[:]

    @log_enter_exit()
    def service_set_stale(self, state):
        """Set service stale state.

        Note: Do not override.
        """

        current = self._service_stored.stale
        if current != state:
            self._service_stored.stale = state
            self.service_set_updated("stale")
            self.service_update_status()

    @log_enter_exit()
    def service_set_state(self, state):
        """Set service sync status for key.

        Note: Do not override.
        """

        current = self._service_stored.state
        synced = self.service_is_synced()

        if state in ["broken", "waiting"]:
            # retry
            state = "started"

        if state == "started":
            if not synced:
                if current in ["broken", "started"]:
                    state = "broken"
                else:
                    state = "waiting"

        if current != state:
            self._service_stored.state = state
            self.service_set_updated("state")
            self.service_update_status()

    @log_enter_exit()
    def service_set_status_message(self, msg=None):
        """Set status message that will show in service_update_status().

        msg of None resets/clears the message (which would then *not*
        be used by the service_update_status()."""

        self._service_stored.status_message = msg

    @log_enter_exit()
    def service_set_sync(self, key, status: Union[bool, None] = None, force=False):
        """Set service sync status for key.

        To trigger handler with current sync value, set status to None or just
        specify a key.

        Note: Do not override.
        """

        # TODO: limit to valid keys
        current = self._service_stored.syncs.get(key)
        if status == None:
            status = current
            force = True

        logger.debug(f"set_sync key ({key}) current ({status}) status ({status})")

        if current == True and status == False:
            import traceback

            logger.debug(f"STATUS key ({key})")

        if current != status or force:
            self._service_stored.syncs[key] = status
            handler = self._service_sync_handlers.get(key)

            if handler:
                try:
                    handler(key, status)
                except Exception as e:
                    logger.debug(f"service sync handler failed ({e})")

            # ensure that state is updated if necessary
            self.service_set_state(self.service_get_state())

            self.service_set_updated("sync")
            self.service_update_status()

    @log_enter_exit()
    def service_set_updated(self, what, timestamp=None):
        """Set service updated timestamp.

        Note: Do not override.
        """

        timestamp = timestamp or get_timestamp()
        self._service_stored.updated = [timestamp, what]

    @log_enter_exit()
    def service_start(self, event):
        """Start service(s).

        Note: Do not override.
        """

        if self.service_get_state() in PRESTARTED_STATES:
            try:
                self.service_sync(event)
                self._service_start(event)
                self.service_set_state("started")
                self.service_set_updated("start")
            except Exception as e:
                logger.debug(f"[{get_methodname(self)} e ({e})")

            self.service_update_status()

    @log_enter_exit()
    def service_stop(self, event, force=False):
        """Stop service(s).

        Note: Do not override.
        """

        if self.service_get_state() in STARTED_STATES:
            try:
                self._service_stop(event, force)
                self.service_set_state("enabled")
                self.service_set_updated("stop")
            except Exception as e:
                logger.debug(f"[{get_methodname(self)} e ({e})")

            self.service_update_status()

    @log_enter_exit()
    def service_update_status(self):
        """Update status.

        Note: Do not override.
        """

        state = self.service_get_state()
        if state in ["broken"]:
            cls = BlockedStatus
        elif state in ["idle", "enabled"]:
            cls = MaintenanceStatus
        elif state in ["waiting"]:
            cls = WaitingStatus
        elif state in ["started"]:
            cls = ActiveStatus
        else:
            cls = MaintenanceStatus

        # TODO: allow for tailoring of status message

        if 1:
            status_message = self._service_stored.status_message
            syncs = self.service_get_syncs()
            nsynced = len([v for v in syncs.values() if v])
            nsyncs = len(syncs)

            msg = f" ({status_message})" if status_message != None else ""

            self.unit.status = cls(
                f"updated ({tuple(self.service_get_updated())})"
                f"{msg}"
                f" stale ({self.service_get_stale()})"
                f" state ({self.service_get_state()})"
                f" synced ({nsynced}/{nsyncs})"
                f" syncs ({syncs})"
            )

        elif 0:
            self.unit.status = cls(
                f"updated ({self.service_get_updated()})"
                f" ({status_message})"
                f"{msg}"
                f" stale ({self.service_get_stale()})"
                f" state ({self.service_get_state()})"
                f" synced ({self.service_is_synced()})"
                f" syncs ({self.service_get_syncs()})"
            )

    @log_enter_exit()
    def service_sync(self, event, force=False):
        """Sync service objects.

        Note: Do not override.
        """

        if self.service_get_state() not in PRESTARTED_STATES and not force:
            # refuse to update while not in prestarted state
            # assume stale configuration
            self.service_set_stale(True)
            self.service_set_updated("sync")
        else:
            try:
                self._service_sync(event)
                self.service_set_stale(False)
                self.service_set_updated("sync")
            except Exception as e:
                import traceback

                logger.debug(f"{traceback.format_exc()}")
                logger.debug(f"[{get_methodname(self)} e ({e})")

        self.service_update_status()

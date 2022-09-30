# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# hpctops/charm/node.py


"""Provides the Node class (built on ServiceCharm) which acts as a
principal charm for a "node".
"""


import logging

from .service import ServiceCharm
from ..misc import log_enter_exit

logger = logging.getLogger(__name__)


class NodeCharm(ServiceCharm):
    """Provide support for nodes.

    Subclasses should call setup_subordinate_relations_and_sync()
    with a list of relation names that are required for this operator
    to "active".
    """

    #
    # registered handlers
    #
    # Note: These methods should *not* be called directly.
    #

    @log_enter_exit()
    def _on_subordinate_relation_joined(self, event):
        """Update associated sync."""

        relname = event.relation.name
        self.service_set_sync(relname, True)

    @log_enter_exit()
    def _on_subordinate_relation_changed(self, event):
        """Update associated sync."""

        relname = event.relation.name
        self.service_set_sync(relname, True)

    def _on_subordinate_relation_departed(self, event):
        """Update associated sync."""

        relname = event.relation.name
        self.service_set_sync(relname, False)

    def setup_subordinate_relations_and_syncs(self, relnames):
        """Set up relation handlers and syncs for subordinates."""

        required_syncs = []
        for relname in relnames:
            urelname = relname.replace("-", "_")
            self.framework.observe(
                getattr(self.on, f"{urelname}_relation_joined"),
                self._on_subordinate_relation_joined,
            )
            self.framework.observe(
                getattr(self.on, f"{urelname}_relation_departed"),
                self._on_subordinate_relation_departed,
            )
            required_syncs.append(relname)
            self.service_init_sync(relname, False)

        self.service_set_required_syncs(required_syncs)

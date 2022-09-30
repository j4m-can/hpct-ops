#
# hpctops/charm/__init__.py
#

"""Support for operators.
"""


def set_base_charm(basecharm):
    """Helper to set/override the ```ops.charm.Charmbase``` that the
    DebuggerCharm will be created with.

    To use, add the following before the new charm is defined:
    ```
    if 1:
        # interpose DebuggerCharm
        from hpctops.charm import set_base_charm
        set_base_charm(ServiceCharm)
        from hpctops.charm.debugger import DebuggerCharm as ServiceCharm
    ```
    """

    import ops.charm

    ops.charm.CharmBase = basecharm

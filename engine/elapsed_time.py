"""Read bounded elapsed time from the existing world clock.

The caller owns its source, saved anchor and observation authority. This helper
only validates the clock coordinates and adds unresolved partial-round slack;
it neither advances time nor creates or resolves an interval.
"""
import common_checks as C


def bounds(engine, clock_anchor, unknown_index, elapsed_base, *, label='elapsed clock'):
    """Return the inclusive known/possible elapsed range for one saved anchor."""
    for value in (clock_anchor, unknown_index, elapsed_base):
        C.integer(value, label, 0)
    if clock_anchor > engine.elapsed_seconds or unknown_index > len(engine.unresolved_time_intervals):
        raise ValueError(label + ' cannot refer to future time')
    low = elapsed_base + engine.elapsed_seconds - clock_anchor
    extra = 0
    for interval in engine.unresolved_time_intervals[unknown_index:]:
        if not isinstance(interval, dict):
            raise ValueError(label + ' needs an actual partial-round interval')
        known = C.integer(interval.get('known_seconds'), label + ' known partial-round time', 0, 9)
        extra += 10 - known
    return low, low + extra

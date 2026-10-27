"""The explicit PTK ch02 Evasion exception, not a common rounding policy."""
import arithmetic_policy as M
from source_context import verified_source


def stat_component(rules, definition, stat):
    """Round only the current stat component; the native owner keeps both caps."""
    rounding = definition['stat_rounding']
    if rounding not in ('floor', 'nearest'):
        raise ValueError('unknown Evasion stat rounding policy')
    if rounding == 'nearest' and definition['per_points'] != 5:
        raise ValueError('PTK ch02 nearest Evasion requires stat / 5')
    verified_source(rules, definition['stat_rounding_source'], label='Evasion stat rounding')
    # Integer stats / 5 cannot tie at .5; nearest is exact floor((stat + 2) / 5).
    return M.ratio(stat + (2 if rounding == 'nearest' else 0), definition['per_points'])

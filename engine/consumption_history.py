"""Read native exposure facts; time windows and rest-scoped histories stay distinct."""
import common_checks as C


def select(records, *, source, when=None, seconds=None, gap_count=None):
    """Return actual rows, never copied authority or a new usage ledger.

    A rest consumer passes its current-rest native list without a time window.
    Time consumers explicitly supply the endpoint and unresolved-time boundary.
    """
    if type(records) is not list or type(source) is not str or not source:
        raise ValueError('native sourced consumption history required')
    timed = when is not None or seconds is not None or gap_count is not None
    if timed:
        C.integer(when,'exposure query time',0)
        C.integer(seconds,'exposure time window',1)
        C.integer(gap_count,'exposure known-time boundary',0)
    found=[];uncertain=False
    for row in records:
        if type(row) is not dict or row.get('source')!=source:
            raise ValueError('actual consumption history source required')
        if timed:
            at=C.integer(row.get('at'),'exposure time',0)
            if when-at>=seconds:continue
            if row.get('gap_count')!=gap_count:uncertain=True
        found.append(row)
    return {'records':found,'count':len(found),'uncertain':uncertain}

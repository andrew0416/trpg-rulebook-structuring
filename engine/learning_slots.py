"""Data-driven weighted capacity channels; reservations never become grants."""
from copy import deepcopy


def occupancy(capacities,items,*,reservations=(),exemptions=None):
    if type(capacities)is not dict or not capacities:raise ValueError('declared slot channels required')
    for channel,limit in capacities.items():
        if type(channel)is not str or not channel or (limit is not None and (type(limit)is not int or limit<0)):
            raise ValueError('nonnegative slot capacity or explicit unlimited required')
    if exemptions is None:exemptions={}
    if type(exemptions)is not dict or set(exemptions)-set(capacities):raise ValueError('known exemption channels required')
    used=dict.fromkeys(capacities,0);reserved=dict.fromkeys(capacities,0);seen=set();item_ids=set();trace=[]
    for kind,rows in [('item',items),('reservation',reservations)]:
        for row in rows:
            if type(row)is not dict or set(row)!={'id','source','weights'}:raise ValueError('identified sourced slot occupancy required')
            identity=row['id'];source=row['source'];weights=row['weights']
            if any(type(v)is not str or not v for v in (identity,source)) or (kind,identity) in seen:
                raise ValueError('distinct sourced slot occupancy required')
            seen.add((kind,identity))
            if kind=='item':item_ids.add(identity)
            if type(weights)is not dict or set(weights)-set(capacities) or any(type(v)is not int or v<0 for v in weights.values()):
                raise ValueError('nonnegative weights in declared slot channels required')
            charged={}
            for channel,weight in weights.items():
                exempt=exemptions.get(channel,{})
                if type(exempt)is not dict or any(type(k)is not str or type(v)is not str or not v for k,v in exempt.items()):
                    raise ValueError('source-bound item exemptions required')
                charge=0 if kind=='item' and identity in exempt else weight
                used[channel]+=charge
                if kind=='reservation':reserved[channel]+=charge
                charged[channel]=charge
            trace.append({**deepcopy(row),'kind':kind,'charged':charged})
    for channel,exempt in exemptions.items():
        if type(exempt)is not dict or set(exempt)-item_ids or any(type(v)is not str or not v for v in exempt.values()):
            raise ValueError('exemption must name an actual occupied item and source')
    overflow={channel:used[channel]-limit for channel,limit in capacities.items() if limit is not None and used[channel]>limit}
    return {'used':used,'reserved':reserved,'overflow':overflow,'valid':not overflow,'trace':trace}

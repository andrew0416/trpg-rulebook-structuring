"""Native activation episodes with source cleanup and started-child completion.

The domain owns its state and physical changes. This record owns only the exact
activation/end occurrence; old completion never selects a newer activation.
"""
KEY='state_episodes'


def validate(actor):
    rows=actor.spec.get(KEY,{})
    if type(rows) is not dict:raise ValueError('native episode originals required')
    for n,(identity,row) in enumerate(rows.items(),1):
        if type(row) is not dict or identity!=actor.entity_id+':episode:'+str(n) or row.get('id')!=identity or row.get('owner_id')!=actor.entity_id:
            raise ValueError('actual activation episode identity required')
        if row.get('phase') not in ('active','waiting_children','ready','ended'):
            raise ValueError('explicit episode end phase required')
        if type(row.get('family')) is not str or not row['family'] or type(row.get('native_ref')) is not dict:
            raise ValueError('native activation address required')
        if row.get('source') is not None and (type(row['source']) is not str or not row['source']):
            raise ValueError('actual episode source or unknown required')
        if type(row.get('children')) is not list or type(row.get('logical_cleanup')) is not bool:
            raise ValueError('explicit source cleanup and native children required')
        if row['phase']=='active':
            if row['logical_cleanup'] or row.get('cause') is not None:raise ValueError('active episode cannot have ended')
        elif not row['logical_cleanup'] or not row.get('cause'):
            raise ValueError('ending episode needs its first cause and logical cleanup')
    return rows


def validate_bindings(actor):
    """Save boundary: current native projections must name their exact episode."""
    rows=validate(actor)
    dream=actor.spec.get('dream_sleep_state',{}).get('active')
    tera=actor.spec.get('terastal_state')
    current={'dream_sleep':dream,'terastal':tera}
    for family,native in current.items():
        if native is None or 'episode_id' not in native:continue # observed legacy state
        row=rows.get(native['episode_id'])
        if row is None or row['family']!=family or row['source']!=native['source']:
            raise ValueError('native state belongs to another activation episode')
        expected={'field':'dream_sleep_state','serial':native['serial']} if family=='dream_sleep' else {'field':'terastal_state','activated_at':native['activated_at']}
        if row['native_ref']!=expected:raise ValueError('native activation address changed')
        active=family=='dream_sleep' or native['active']
        if active!=(row['phase']=='active'):raise ValueError('native state and episode phase disagree')
    for identity,row in rows.items():
        if row['family'] in current and row['phase']=='active':
            native=current[row['family']]
            if native is None or native.get('episode_id')!=identity:
                raise ValueError('active episode lost its actual native state')
    return rows


def require(actor, identity, *, family):
    row=validate(actor).get(identity)
    if row is None or row['family']!=family:raise ValueError('actual '+family+' episode required')
    return row


def start(actor, *, family, source, native_ref):
    rows=validate(actor)
    if source is not None and (type(source) is not str or not source):raise ValueError('actual episode source or unknown required')
    if type(family) is not str or not family or type(native_ref) is not dict or not native_ref:
        raise ValueError('native activation address required')
    identity=actor.entity_id+':episode:'+str(len(rows)+1)
    row={'id':identity,'owner_id':actor.entity_id,'family':family,'source':source,
         'native_ref':dict(native_ref),'phase':'active','logical_cleanup':False,
         'cause':None,'children':[]}
    actor.spec.setdefault(KEY,{})[identity]=row
    return identity


def end(actor, identity, *, cause, cleanup, children=(), child_complete=None, physical=None):
    """Cleanup once, wait for exact started children, then commit physical end.

    Call within the native transaction. Child references are actual native
    records, not copied booleans. Validation of their authority stays with the
    supplied native completion reader, which must be present for any children.
    """
    row=validate(actor).get(identity)
    if row is None:raise ValueError('actual activation episode required')
    if type(cause) is not str or not cause:raise ValueError('actual state end cause required')
    if row['phase']=='ended':return row
    if row['phase']=='active':
        if not isinstance(children,(list,tuple)) or (children and not callable(child_complete)):
            raise ValueError('native child references and completion reader required')
        # Validate all child bindings before source cleanup.
        for child in children:
            if type(child_complete(child)) is not bool:raise ValueError('native child completion must be boolean')
        cleanup()
        row.update(cause=cause,logical_cleanup=True,children=list(children),phase='waiting_children')
    if row['children'] and not callable(child_complete):raise ValueError('native child completion reader required')
    completions=[child_complete(child) for child in row['children']]
    if any(type(done) is not bool for done in completions):raise ValueError('native child completion must be boolean')
    if not all(completions):return row
    row['phase']='ready'
    if physical is not None:physical()
    row['phase']='ended'
    return row

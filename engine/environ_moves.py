"""C10-295: current observed region selects the native Environ Move state.

The spatial/environment owners retain region identity, change lifetime and
restoration. This adapter does not invent a biome from weather or rough terrain.
"""
from copy import deepcopy
import environment_derive as ED
import environment_change as EC
from source_context import verified_source

NATURE='move/자연의힘'
SECRET='move/비밀의힘'
SOURCE={'file':'input/ch10-index-reference.md','sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}
MOVE_SOURCE={'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'}
ORIGINAL={
    NATURE:{'effects_exec':[{'type':'random_move','source':'환경 키워드 표 (by terrain)'}]},
    SECRET:{'effects_exec':[{'type':'environment_effect','table':'환경 키워드','on_natural_roll_min':17}]},
}
TABLE={
    '초원':('move/풀묶기',{'type':'apply_status','status':'잠듦'}),
    '숲':('move/에너지볼',{'type':'apply_status','status':'잠듦'}),
    '늪지':('move/진흙폭탄',{'type':'stage_change','stat':'spe','delta':-1}),
    '바다':('move/거품광선',{'type':'stage_change','stat':'atk','delta':-1}),
    '설원':('move/오로라빔',{'type':'apply_status','status':'얼음'}),
    '산':('move/파워젬',{'type':'apply_status','status':'풀죽음'}),
    '동굴':('move/원시의힘',{'type':'apply_status','status':'풀죽음'}),
    '도시':('move/트라이어택',{'type':'apply_status','status':'마비'}),
    '사막':('move/대지의힘',{'type':'stage_change','stat':'acc','delta':-1}),
}


def prepare(e,actor,move):
    if move['id'] not in (NATURE,SECRET):return move
    verified_source(e.r,SOURCE,label='Environ table')
    verified_source(e.r,MOVE_SOURCE,label='Environ Move')
    if e.r._selected_rule(move['id'])!=move['id']:raise ValueError('selected Environ Move source changed')
    current=ED.region(e,actor);effective=EC.effective(e,current);environ=effective.get('environ')
    environ,adaptive=__import__('survivalist_class').environ_as_if(e,actor,environ)
    if environ not in TABLE:raise ValueError('current observed Environ environment is unknown')
    selected,effect=TABLE[environ]
    changes=[deepcopy(EC._state(e)['requests'][uid]) for uid in EC._state(e)['active']
        if EC._state(e)['requests'][uid]['region_id']==current['id']]
    selection=ED._sign(dict(actor_id=actor.entity_id,region_id=current['id'],environ=environ,
        region_sha256=current['sha256'],region_snapshot=deepcopy(current),
        selected_at=e.elapsed_seconds,change_snapshots=changes,effective_facts=effective,
        selected_move=selected,secondary_effect=deepcopy(effect),adaptive_geography=adaptive))
    out=deepcopy(move)
    if move['id']==NATURE:
        if e.r._selected_rule(selected)!=selected:raise ValueError('selected Nature Power result source changed')
        native=e.r.move(selected)
        # The actual chosen Move supplies its attack fields; Nature Power owns
        # its one action, known-Move permission, identity and frequency account.
        for key in ('type','class','damage_base','ac','range','keywords'):
            if key in native:out[key]=deepcopy(native[key])
    out['_environ_selection']=selection
    return out


def _selection(e,move,actor=None):
    selection=move.get('_environ_selection')
    if selection is None:raise ValueError('native Environ Move requires a prepared environment selection')
    ED._verify(selection)
    if set(selection)!={'actor_id','region_id','environ','region_sha256','region_snapshot','selected_at','change_snapshots','effective_facts','selected_move','secondary_effect','adaptive_geography','sha256'}:
        raise ValueError('exact prepared Environ selection fields required')
    import world_entities as W
    actual=W.actor_index(e).get(selection['actor_id'])
    if actual is None or (actor is not None and actual is not actor):raise ValueError('actual Environ actor identity changed')
    snapshot=selection['region_snapshot'];ED._verify(snapshot)
    ED.Q._fields({k:v for k,v in snapshot.items() if k!='sha256'},('id','source','facts','cells','reason','seconds'))
    if snapshot.get('id')!=selection['region_id'] or snapshot['sha256']!=selection['region_sha256'] or selection['region_id'] not in ED._state(e)['regions']:
        raise ValueError('actual prepared Environ region identity changed')
    current=ED._state(e)['regions'][selection['region_id']];ED._verify(current)
    if current['sha256']!=snapshot['sha256'] or current!=snapshot:raise ValueError('actual prepared Environ region changed')
    ED.facts(snapshot['facts']);ED.Q._selected(e,snapshot['source'])
    ED.C.integer(selection['selected_at'],'Environ selection time',0)
    if selection['selected_at']>e.elapsed_seconds:raise ValueError('actual Environ selection time required')
    changes=selection['change_snapshots']
    if type(changes) is not list:raise ValueError('actual Environ change witnesses required')
    # Reconstruct the owner's active order at selection from immutable request
    # insertion order. A later request replaces that region/source even when
    # it is permanent or has already expired; an older request never revives.
    requests=EC._state(e)['requests'];latest={}
    for uid,row in requests.items():
        if row['region_id']==snapshot['id'] and row['started_at']<=selection['selected_at']:
            ED._verify(row);latest[row['source']]=uid
    expected=[row for uid,row in requests.items() if latest.get(row['source'])==uid
        and row['expires_at'] is not None and selection['selected_at']<row['expires_at']]
    if changes!=expected:raise ValueError('prepared Environ active change witnesses changed')
    effective=deepcopy(snapshot['facts']);seen=set()
    for row in changes:
        ED._verify(row);uid=row.get('request_id');actual_row=EC._state(e)['requests'].get(uid)
        if uid in seen or actual_row!=row:raise ValueError('actual Environ change witness changed')
        seen.add(uid);ED.Q._selected(e,row['source'])
        if row['region_id']!=snapshot['id'] or row['expires_at'] is None or not row['started_at']<=selection['selected_at']<row['expires_at']:
            raise ValueError('Environ change witness was not active at selection')
        effective.update(row['changes'])
    # Retained immutable requests prove the action's prepared selection even
    # after a temporary change expires. Current active rows are not reapplied.
    if ED.facts(effective)!=ED.facts(selection['effective_facts']) or effective.get('environ')!=__import__('survivalist_class').environ_selection_actual(selection):
        raise ValueError('prepared Environ selection differs from its effective facts')
    selected=TABLE.get(selection['environ'])
    if selected is None or (selection['selected_move'],selection['secondary_effect'])!=selected:
        raise ValueError('prepared Environ selection differs from the source table')
    verified_source(e.r,SOURCE,label='Environ table');verified_source(e.r,MOVE_SOURCE,label='Environ Move')
    if e.r._selected_rule(move['id'])!=move['id'] or e.r._selected_rule(selected[0])!=selected[0]:
        raise ValueError('selected Environ source changed')
    return selection


def mechanics(e,move,original,*,actor=None):
    if move['id'] not in (NATURE,SECRET):
        if '_environ_selection' in move:raise ValueError('prepared Environ Move identity changed')
        return original
    selection=_selection(e,move,actor)
    if original!=ORIGINAL[move['id']]:raise ValueError('selected Environ source mechanics need an explicit policy')
    if move['id']==NATURE:
        return deepcopy(e.r.move_mech(selection['selected_move'])[0])
    if move['id']==SECRET:
        effect=dict(deepcopy(selection['secondary_effect']),target='target',on_natural_roll_min=17)
        return dict(deepcopy(original),effects_exec=[effect])
    raise ValueError('prepared Environ Move identity changed')


def read(e,move,actor=None):
    """Keep the selected mechanics on native accuracy/damage re-reads."""
    original,confidence=e.r.move_mech(move['id'])
    mm=mechanics(e,move,original,actor=actor)
    return __import__('rune_master').mechanics(e,actor,move,mm),confidence

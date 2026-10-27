"""Rune Master: acquired sources compose native Unown, Move and object owners."""
from copy import deepcopy
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import csv
import json
import re

import common_checks as C
import state_grants as G
import world_entities as W
import special_entities as SPECIAL

CLASS='supp-fantasy/룬마스터'
POWER='feat/잠재파워'; REWRITE='feat/덮어쓰기'; GLYPH='feat/상형문자'
WORDS='feat/단어의-힘'; ALARM='feat/알람-룬'; EXPLOSIVE='feat/폭발-룬'; SENTRY='feat/센트리-룬'
HP='move/잠재파워'; GATHER='capability/안농-모으기'; PRESS='capability/활자'
BOOK_SHA='a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
FEATURES={CLASS:(598,600),POWER:(602,606),REWRITE:(608,613),GLYPH:(615,621),
          WORDS:(623,628),ALARM:(630,637),EXPLOSIVE:(639,644),SENTRY:(646,655)}
CSV_ROWS={CLASS:551,POWER:552,REWRITE:553,WORDS:554,GLYPH:555,ALARM:556,EXPLOSIVE:557,SENTRY:558}
PARENTS={CLASS:(),POWER:(CLASS,),REWRITE:(POWER,),GLYPH:(CLASS,),WORDS:(POWER,),
         ALARM:(GLYPH,),EXPLOSIVE:(GLYPH,POWER),SENTRY:(GLYPH,POWER)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[585,656] if u==CLASS else list(s),
    'clause_id':{CLASS:'FAN-073',POWER:'FAN-074',REWRITE:'FAN-075',GLYPH:'FAN-076',WORDS:'FAN-077',ALARM:'FAN-078',EXPLOSIVE:'FAN-079',SENTRY:'FAN-080'}[u],
    'parents':list(PARENTS[u]),'minimum_occult':3 if u==CLASS else 4 if u in (WORDS,EXPLOSIVE) else 5 if u==SENTRY else 0,
    'source_choices':['supplement','local_csv'],'stat_tags':['atk','spa'],'minimum_level':0,'skill':None} for u,s in FEATURES.items()}


def _type_table(rules):
    # The selected native Move is the authority, including Error and reroll20.
    text=rules.move(HP)['effect']
    table={int(n):kind for n,kind in re.findall(r'(\d+)일때\s*([가-힣]+)',text) if 1<=int(n)<=19}
    if set(table)!=set(range(1,20)):raise ValueError('complete selected native Hidden Power d20 table required')
    return table


def _roll_type(e,fixed_d20=None):
    import roll_pools as POOLS
    table=_type_table(e.r)
    if fixed_d20 is not None:
        if type(fixed_d20) not in (list,tuple) or not fixed_d20:raise ValueError('actual Hidden Power d20 faces required')
        for face in fixed_d20:C.integer(face,'Hidden Power d20 face',1,20)
        if any(v!=20 for v in fixed_d20[:-1]) or fixed_d20[-1]==20:raise ValueError('twenties reroll until an actual 1 through 19 result')
    index=0
    while True:
        face=POOLS.die(e.rng,20,fixed=None if fixed_d20 is None else fixed_d20[index]);index+=1
        if face!=20:return table[face]


def _is_power(move):
    return move.get('name','').startswith('잠재파워') or move.get('eng','').startswith('Hidden Power')


def records(actor, feature=None, active=False):
    import trainer_feature_acquisition as T
    return [r for _,r in T.static_family_acquisitions(actor,FEATURES,feature,active=active)]


def acquired(actor, feature=CLASS):
    rows=records(actor,feature,True)
    return rows[-1] if rows else None


def source(rules, feature, edition):
    from source_context import verified_source
    if feature not in FEATURES or edition not in ('supplement','local_csv'):
        raise ValueError('exact Rune Master Feature and source edition required')
    if rules._selected_rule(feature)!=feature or feature in rules.ruleset.unit_versions:
        raise ValueError('selected Rune Master source needs its explicit adapter')
    verified_source(rules,{'file':'input/supp-fantasy.md','sha256':BOOK_SHA},label='Rune Master supplement')
    result={'edition':edition,'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'span':list(FEATURES[feature])}
    if edition=='local_csv':
        content=verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Rune Master CSV')
        # Hash the complete physical row, including its multiline cell boundaries.
        with (Path(rules.root)/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:
            cells=list(csv.reader(stream))[CSV_ROWS[feature]-1]
        rules.ruleset.require({'id':'C2CSV/input/db/feats.csv:R'+str(CSV_ROWS[feature])+':main',
                              'source':{'file':'db/feats.csv','record_span':[CSV_ROWS[feature]]*2}})
        result.update(file='input/db/feats.csv',sha256=CSV_SHA,row=CSV_ROWS[feature],
                      cells_sha256=sha256(json.dumps(cells,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    return result


def static_source(rules,feature):
    source(rules,feature,'supplement')
    actual=rules.selection.units[feature].get('source',{})
    if actual.get('file')!='supp-fantasy.md' or actual.get('lines')!=DEFINITIONS[feature]['catalog_span'] or actual.get('sha256')!=BOOK_SHA:
        raise ValueError('exact original Rune Master catalog source required')
    return {'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'clause_id':DEFINITIONS[feature]['clause_id'],'span':list(FEATURES[feature])}


def _owned_unown(e,actor):
    consumed={r.get('unown_id') for r in getattr(e,'_physical_objects',{}).values() if r.get('kind')=='glyph'}
    return [p for p in W.actor_index(e).values() if p.kind=='pokemon' and
            e.r.species.get(p.spec.get('species'),{}).get('name') in ('안농','Unown') and
            p.entity_id not in consumed and p.spec.get('trainer_id')==actor.entity_id]


def acquisition_snapshot(e,actor,feature,rank,selection):
    import skill_modifiers as SK
    if rank is not None:raise ValueError('Rune Master Features are not Ranked')
    if type(selection)is not dict or set(selection)!={'edition','stat'} or selection['stat'] not in ('atk','spa'):
        raise ValueError('explicit Rune Master edition and Attack or Special Attack tag required')
    src=source(e.r,feature,selection['edition'])
    parents=(EXPLOSIVE,POWER) if feature==SENTRY and selection['edition']=='local_csv' else PARENTS[feature]
    return {'selection':deepcopy(selection),'source':src,'rank':SK.rank(e.r,actor,'오컬트학')[2],
            'parents':[r['request_id'] for r in records(actor,active=True) if r['feature_id'] in parents],
            'owned_unown':[p.entity_id for p in _owned_unown(e,actor)]}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'selection','source','rank','parents','owned_unown'}:
        raise ValueError('exact Rune Master acquisition observations required')
    chosen=snapshot['selection']
    if type(chosen)is not dict or set(chosen)!={'edition','stat'} or chosen['stat'] not in ('atk','spa'):
        raise ValueError('exact Rune Master source and stat tag required')
    if snapshot['source']!=source(actor.r,feature,chosen['edition']):raise ValueError('Rune Master acquisition source changed')
    C.integer(snapshot['rank'],'acquired Occult Education rank',1)
    parents=(EXPLOSIVE,POWER) if feature==SENTRY and chosen['edition']=='local_csv' else PARENTS[feature]
    history={r['request_id']:r['feature_id'] for r in records(actor)}
    if type(snapshot['parents'])is not list or not set(snapshot['parents'])<=set(history):raise ValueError('actual Rune parent acquisition receipts required')
    ids=snapshot['owned_unown']
    if type(ids)is not list or len(set(ids))!=len(ids) or any(type(v)is not str or not v for v in ids):raise ValueError('distinct actual owned Unown required')
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('parents','prerequisite',set(parents)<={history[r] for r in snapshot['parents']},'printed Rune Master parents required'),
        Q.check('occult','prerequisite',snapshot['rank']>=DEFINITIONS[feature]['minimum_occult'],'printed Occult Education rank required'),
        Q.check('unown','prerequisite',feature!=CLASS or len(ids)>=2,'two actually owned Unown required')])


def after_acquire(e,actor,feature,sid):
    chosen=acquired(actor,feature)['snapshot']['selection']
    G.stat(actor,chosen['stat'],1,sid,operation_id='acquisition_stat_tag')
    if feature==CLASS:
        G.grant(actor,'capabilities',GATHER,sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=CLASS)
    if feature==POWER:
        G.grant_moves(actor,[HP],sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=POWER)
        # The normal random-on-learn table owns this permanent instance choice.
        if 'hidden_power_type' not in actor.spec:actor.spec['hidden_power_type']=_roll_type(e)


def validate_acquisition(actor,record,sid,active):
    if not active:return
    chosen=record['snapshot']['selection'];row=actor.spec.get(G.KEY,{}).get('sources',{}).get(sid,{})
    if actor.spec[G.KEY].get('stat_sources',{}).get(chosen['stat'],{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:
        raise ValueError('actual Rune Master stat tag required')
    if record['feature_id']==CLASS and GATHER not in row.get('grants',{}).get('capabilities',[]):raise ValueError('actual Gather Unown source grant required')
    if record['feature_id']==POWER:
        if HP not in row.get('grants',{}).get('moves',[]) or actor.spec.get('hidden_power_type') not in _type_table(actor.r).values():raise ValueError('actual learned permanent Hidden Power instance required')


def require(e,actor,feature):
    W.require_actors(e,actor)
    if not acquired(actor,feature):raise ValueError('actual acquired Rune Master Feature required: '+feature)
    source(e.r,feature,acquired(actor,feature)['snapshot']['selection']['edition'])
    __import__('trainer_feature_acquisition').validate_actor(actor)
    if actor.fainted or actor.dead or actor.captured or not actor.on_field:raise ValueError('available actual Rune Master required')


def reconcile_unown(e):
    """Refresh only Rune-owned PRESS sources at the existing grant boundary."""
    index=W.actor_index(e);owners={}
    for actor in index.values():
        if actor.kind!='trainer':continue
        rows=[(sid,row) for sid,row in actor.spec.get(G.KEY,{}).get('sources',{}).items()
              if row.get('static_acquisition',{}).get('feature_id')==CLASS]
        if rows:owners[actor.entity_id]=(actor,rows[-1][0])
    consumed={row.get('unown_id') for row in getattr(e,'_physical_objects',{}).values() if row.get('kind')=='glyph'}
    for pokemon in index.values():
        if pokemon.kind!='pokemon':continue
        original=pokemon.spec.get(G.KEY,{}).get('sources',{})
        owner=owners.get(pokemon.spec.get('trainer_id'))
        eligible=bool(owner and pokemon.entity_id not in consumed and
            e.r.species.get(pokemon.spec.get('species'),{}).get('name') in ('안농','Unown'))
        stale=[sid for sid,row in original.items() if row.get('rule_id')==CLASS and
            row.get('lifetime')=='your_pokemon' and PRESS in row.get('grants',{}).get('capabilities',[]) and
            (not eligible or sid!=owner[1] or row.get('owner_id')!=owner[0].entity_id)]
        if stale:G._revoke_sources(pokemon,stale,e)
        if eligible and PRESS not in pokemon.spec.get(G.KEY,{}).get('sources',{}).get(owner[1],{}).get('grants',{}).get('capabilities',[]):
            G.grant(pokemon,'capabilities',PRESS,owner[1],'feature',owner_id=owner[0].entity_id,lifetime='your_pokemon',rule_id=CLASS)


def gather_authorized(e,actor):
    if actor.kind!='trainer' or not acquired(actor):return False
    require(e,actor,CLASS)
    return GATHER in G.effective(actor,'capabilities')


def _powers(actor):
    return [mid for mid in actor.moves if _is_power(actor.r.move(mid))]


def _power_type(actor,mid):
    for row in reversed(list(actor.spec.get(G.KEY,{}).get('sources',{}).values())):
        if mid in row.get('hidden_power_types',{}):return row['hidden_power_types'][mid]
    kind=actor.spec.get('hidden_power_type') if mid==HP else actor.r.move(mid).get('type')
    if kind not in _type_table(actor.r).values():raise ValueError('actual permanent Hidden Power type observation required')
    return kind


def _pay(e,actor,feature,action='standard',ap=0,automatic=False):
    import action_points as AP,turn as TURN
    if AP.available(actor)<ap:raise ValueError('available Rune Master AP required')
    if automatic and feature!=EXPLOSIVE:__import__('action_lifecycle').triggered_free_action(e,actor,feature)
    elif automatic:pass  # Its authenticated native Hidden Power owns the Free Action.
    elif action and not TURN.spend(e,actor,action,feature):raise ValueError('Rune Master requires '+action+' action')
    if ap:AP.charge(actor,ap)


def rewrite(e,actor,target,*,move_id=None,letter=None,fixed_d20=None):
    require(e,actor,REWRITE);W.require_actors(e,target)
    if target is not actor and target.kind!='pokemon':raise ValueError('Rewrite targets self or an actual Pokemon')
    powers=_powers(target)
    if move_id is None and len(powers)==1:move_id=powers[0]
    if move_id not in powers:raise ValueError('select one actual known Hidden Power instance')
    if letter is not None:
        SPECIAL._unown(e,target);W._text(letter,'chosen Unown letter')
    import frequency as F
    quota={'kind':'daily','uses':1}
    if not F.activation_allowed(actor,REWRITE,quota,engine=e):raise ValueError('Rewrite daily frequency exhausted')
    def apply(se,a,t=None):
        if t is None:t=a
        F.consume_activation(a,REWRITE,quota,engine=se)
        sid='rewrite:'+a.entity_id+':'+t.entity_id
        row=G._source(t,sid,'feature',owner_id=a.entity_id,rule_id=REWRITE,lifetime='permanent',tutor_points=0)
        kind=_roll_type(se,fixed_d20);changes={move_id:kind}
        if move_id==HP:t.spec['hidden_power_type']=kind
        else:row.setdefault('hidden_power_types',{})[move_id]=kind
        if letter is not None:t.spec['unown_letter']=letter
        return {'source':REWRITE,'target_id':t.entity_id,'types':changes,'letter':letter}
    return G.transition(e,actor,apply,participants=() if target is actor else (target,))


def _glyph(e,actor,glyph_id,*,active=True):
    row=getattr(e,'_physical_objects',{}).get(glyph_id)
    if not row or row.get('kind')!='glyph' or row.get('creator_id')!=actor.entity_id:raise ValueError('one Glyph actually placed by this Rune Master required')
    SPECIAL.validate_record(e,row)
    if active and row['status']!='active':raise ValueError('active unconsumed Glyph required')
    return row


def _payload(actor,feature):
    current=acquired(actor,feature)
    if current is None:raise ValueError('actual Rune Master source payload required')
    return next(row for row in G.state(actor)['sources'].values() if row.get('static_acquisition',{}).get('request_id')==current['request_id'])


def create_glyph(e,actor,unown,*,glyph_id,surface_id,visible,seconds,flat_surface,contact,gm_id,reason):
    require(e,actor,GLYPH);W.require_actors(e,unown);SPECIAL._unown(e,unown)
    if type(visible)is not bool:raise ValueError('explicit Glyph visibility choice required')
    C.integer(seconds,'GM-adjudicated Extended Action seconds',1);W._text(reason,'Extended Glyph duration reason')
    surface=getattr(e,'_physical_objects',{}).get(surface_id)
    W._text(gm_id,'actual flat-surface GM observer')
    if surface is None or flat_surface is not True:raise ValueError('actual GM-observed flat physical surface required')
    if contact is not True:raise ValueError('GM-observed actual pressing contact with that surface required')
    for subject in (actor,unown):
        distance=W.distance_known(subject,surface)
        if distance is not None and distance>1:raise ValueError('known location contradicts actual surface pressing contact')
    if glyph_id in W.entity_index(e):raise ValueError('fresh Glyph identity required')
    SPECIAL.require_prime_independent(e,unown)
    if any(row.get('kind')=='prime_unown' and row['actor_id']==unown.entity_id for row in getattr(e,'_physical_objects',{}).values()):raise ValueError('Prime Unown cannot become a Glyph')
    location=deepcopy(surface['location'])
    import activity_jobs as JOB
    def apply(se,a,u):
        job_id='glyph:'+glyph_id
        JOB.start(se,a,(u,),job_id=job_id,source=GLYPH,definition={'required_seconds':seconds},
                  context={'surface_id':surface_id,'flat_surface':True,'contact':True,'gm_id':gm_id,'reason':reason})
        JOB.advance(se,job_id,interval_id=job_id+'/work',seconds=seconds)
        u.on_field=False;u.location=location
        row=dict(id=glyph_id,kind='glyph',location=location,creator_id=a.entity_id,unown_id=u.entity_id,
                 creation_level=a.level,level=a.level,hp=a.level,max_hp=a.level,status='active',visible=visible,channeling=False,flat_surface_id=surface_id)
        result=SPECIAL.observe(se,row,reason=reason)
        _payload(a,GLYPH).setdefault('rune_glyphs',{})[glyph_id]={'job_id':job_id,'created_at':se.elapsed_seconds}
        return result
    return G.transition(e,actor,apply,participants=(unown,))


def channel(e,actor,glyph_id,*,enabled=True):
    require(e,actor,GLYPH);_glyph(e,actor,glyph_id)
    if type(enabled)is not bool:raise ValueError('explicit channel state required')
    def apply(se,a):
        _pay(se,a,GLYPH)
        for row in getattr(se,'_physical_objects',{}).values():
            if row.get('kind')=='glyph' and row.get('creator_id')==a.entity_id:row['channeling']=False
        row=_glyph(se,a,glyph_id);row['channeling']=enabled
        if enabled:row['visible']=True
        return SPECIAL.view(se,glyph_id)
    return G.transition(e,actor,apply)


def observe_glyph(e,actor,glyph_id,*,sights,sounds,gm_id,reason):
    require(e,actor,GLYPH);row=_glyph(e,actor,glyph_id)
    if not row['channeling']:raise ValueError('currently channeled Glyph required')
    for label,value in (('actual GM',gm_id),('Glyph sensory reason',reason)):W._text(value,label)
    if any(type(v)is not list or any(type(x)is not str for x in v) for v in (sights,sounds)):raise ValueError('explicit actual Glyph sights and sounds required')
    fact={'glyph_id':glyph_id,'location':deepcopy(row['location']),'sights':deepcopy(sights),'sounds':deepcopy(sounds),'gm_id':gm_id,'reason':reason,'at':e.elapsed_seconds}
    _payload(actor,GLYPH)['glyph_senses']=fact
    return deepcopy(fact)


def speak(e,actor,glyph_id,message):
    require(e,actor,GLYPH);row=_glyph(e,actor,glyph_id)
    if not row['channeling']:raise ValueError('currently channeled Glyph required')
    W._text(message,'actual projected Glyph voice')
    out={'speaker_id':actor.entity_id,'origin':deepcopy(row['location']),'message':message}
    e.log('Glyph voice: '+message,GLYPH)
    return out


def end_glyph(e,actor,glyph_id,*,damage=None,deactivate=False):
    require(e,actor,GLYPH);_glyph(e,actor,glyph_id)
    if type(deactivate)is not bool or damage is None and not deactivate:raise ValueError('actual Glyph damage or intentional deactivation required')
    if damage is not None:C.integer(damage,'actual Glyph HP loss',0)
    def apply(se,a):
        row=_glyph(se,a,glyph_id)
        if damage is not None:row['hp']=max(0,row['hp']-damage)
        if deactivate or row['hp']==0:
            row['status']='deactivated' if deactivate else 'destroyed';row['channeling']=False
            _stop_alarm(se,a,glyph_id,automatic=True)
        return SPECIAL.view(se,glyph_id)
    return G.transition(e,actor,apply)


@contextmanager
def _using(e,actor,mid,damage_class,shape,glyph_id=None,prepaid=False,targets=()):
    if getattr(e,'_rune_move',None)is not None:raise ValueError('one actual Rune Move at a time')
    e._rune_move={'actor':actor,'move_id':mid,'class':damage_class,'shape':shape,'glyph_id':glyph_id,'prepaid':prepaid,'targets':tuple(targets)}
    try:yield
    finally:del e._rune_move


def _scope(e,actor,move):
    scope=getattr(e,'_rune_move',None)
    return scope if scope and scope['actor'] is actor and scope['move_id']==move['id'] else None


def move_authority(e,actor,target,move_id,source):
    scope=_scope(e,actor,{'id':move_id})
    if source!=EXPLOSIVE or scope is None or not scope['prepaid']:return False
    if not scope['glyph_id'] or target not in scope['targets']:raise ValueError('actual paid Explosive Rune activation required')
    require(e,actor,EXPLOSIVE);_glyph(e,actor,scope['glyph_id'])
    return True


def prepare(e,actor,move):
    if not _is_power(move):return move
    scope=_scope(e,actor,move)
    if scope is None:return move
    ranges={'burst':'파열 1','melee':'근접, 대상 1','ranged':'6, 대상 1','cone':'원뿔 2'}
    spec={'burst':{'shape':'burst','size':1,'origin':'self'},'melee':{'origin':'melee','targets':1},
          'ranged':{'origin':6,'targets':1},'cone':{'shape':'cone','size':2,'origin':'self'}}[scope['shape']]
    return dict(move,type=_power_type(actor,move['id']),**{'class':scope['class']},range=ranges[scope['shape']],
                _class_move_range=dict(spec,raw=ranges[scope['shape']],parsed=True),_rune_power=True)


def mechanics(e,actor,move,mm):
    if not move.get('_rune_power'):return mm
    if _scope(e,actor,move)is None:raise ValueError('actual Rune Hidden Power activation required')
    return dict(mm,effects_exec=[x for x in mm.get('effects_exec',[]) if x.get('type')!='random_type_on_learn'])


def grants_stab(e,actor,move):
    if not _is_power(move):return False
    if acquired(actor,WORDS):return True
    for row in getattr(e,'_physical_objects',{}).values():
        if row.get('kind')=='prime_unown' and row.get('actor_id')==actor.entity_id:
            owner=W.actor_index(e).get(actor.spec.get('trainer_id'))
            return bool(owner and acquired(owner,WORDS))
    return False


def range_actor(e,actor,move):
    scope=_scope(e,actor,move)
    if not scope or not scope['glyph_id']:return actor
    glyph=_glyph(e,actor,scope['glyph_id'])
    return W.actor_index(e)[glyph['unown_id']]


def selected_targets(e,actor,move,candidates,primary):
    scope=_scope(e,actor,move)
    if not scope or not scope['glyph_id']:return None
    import body_state as BODY,weapon_actions as WEAPONS
    origin=range_actor(e,actor,move);rng=WEAPONS.range_spec(e,move,actor)
    if e.grid is None:raise ValueError('remote Glyph attack requires actual observed map geometry')
    if rng.get('shape')=='burst':cells=e.grid.burst(origin.pos,1)
    elif rng.get('shape')=='cone':
        dx=(primary.pos[0]>origin.pos[0])-(primary.pos[0]<origin.pos[0]);dy=(primary.pos[1]>origin.pos[1])-(primary.pos[1]<origin.pos[1])
        cells=e.grid.cone(origin.pos,(dx or (1 if not dy else 0),dy),2)
    else:return [primary] if primary in candidates and BODY.in_range(e,origin,primary,1 if rng['origin']=='melee' else rng['origin']) else []
    return [p for p in candidates if BODY.cells(p,require_complete=True).intersection(cells)]


def use_power(e,actor,target,targets,*,move_id=HP,damage_class,shape='burst',trainer=None):
    if trainer is None:require(e,actor,POWER)
    else:
        require(e,trainer,WORDS);W.require_actors(e,actor)
        if actor.kind!='pokemon' or actor.spec.get('trainer_id')!=trainer.entity_id:raise ValueError('Words of Power requires actual owned Pokemon')
        if damage_class!=e.r.move(move_id).get('class'):raise ValueError('Words of Power changes area, not the Pokemon Move damage class')
    if move_id not in _powers(actor) or damage_class not in ('물리','특수'):raise ValueError('actual learned Hidden Power and selected damage class required')
    if shape not in ('burst','melee','ranged','cone') or shape!='burst' and not acquired(trainer or actor,WORDS):raise ValueError('Words of Power required for alternate area')
    def apply(se,a,t,*others):
        with _using(se,a,move_id,damage_class,shape):
            if trainer is not None:
                owner=W.actor_index(se)[trainer.entity_id]
                return se.pokemon_activity(owner,'command_move',pokemon=a,target=t,move_id=move_id)
            return se.use_move_on(a,t,move_id,[t,*others])
    group=list(dict.fromkeys([target,*targets]));W.require_actors(e,*group)
    return G.transition(e,actor,apply,participants=tuple(group))


def explosive(e,actor,glyph_id,target,targets,*,move_id=HP,damage_class='특수',shape='burst',automatic=False):
    require(e,actor,EXPLOSIVE);_glyph(e,actor,glyph_id)
    if move_id not in _powers(actor) or damage_class not in ('물리','특수'):raise ValueError('actual creator Hidden Power instance required')
    if shape not in ('burst','melee','ranged','cone') or shape!='burst' and not acquired(actor,WORDS):raise ValueError('Words of Power required for alternate area')
    if automatic and not _automatic(e,actor,glyph_id,'explosive'):raise ValueError('actual triggered Alarm automatic permission required')
    group=list(dict.fromkeys([target,*targets]));W.require_actors(e,*group)
    def apply(se,a,t,*others):
        _pay(se,a,EXPLOSIVE,ap=0 if automatic else 1,automatic=automatic)
        row=_glyph(se,a,glyph_id);row['visible']=True
        _payload(a,EXPLOSIVE).setdefault('glyph_glow',{})[glyph_id]=se.elapsed_seconds+60
        with _using(se,a,move_id,damage_class,shape,glyph_id,prepaid=True,targets=tuple([t,*others])):
            before=set(getattr(se,'_move_completions',{}))
            result=se.use_move_on(a,t,move_id,[t,*others])
            rows=[r for key,r in getattr(se,'_move_completions',{}).items() if key not in before]
            if not rows or any(r['phase']!='complete' for r in rows):raise ValueError('actual whole Explosive Rune activation must complete')
            return result
    return G.transition(e,actor,apply,participants=tuple(group))


def sentry(e,actor,glyph_id,*,entity_id,investment,move_id=HP,automatic=False):
    require(e,actor,SENTRY);glyph=_glyph(e,actor,glyph_id)
    if move_id not in _powers(actor):raise ValueError('one actual creator Hidden Power instance required')
    if any(row.get('kind')=='sentry' and row.get('creator_id')==actor.entity_id and row.get('status')=='active' for row in getattr(e,'_physical_objects',{}).values()):raise ValueError('only one active Sentry per creator')
    if entity_id in W.entity_index(e):raise ValueError('fresh actual Sentry identity required')
    if automatic and not _automatic(e,actor,glyph_id,'sentry'):raise ValueError('actual triggered Alarm automatic permission required')
    from builder import build_pokemon,species_lookup,calc
    import growth_stats as GROWTH,arithmetic_policy as M
    plan=GROWTH.compose(species_lookup(e.r,'안농')['base_stats'],investment,
                       points=M.floor(calc(e.r.mech('pokemon/stat-build')['stat_points'],{'level':actor.level})),rules=e.r)
    def apply(se,a):
        _pay(se,a,SENTRY,ap=0 if automatic else 1,automatic=automatic)
        from engine import Combatant
        spec=build_pokemon(se.r,'안농',a.level,moves=[move_id],abilities=[],wild=True,side=a.side,
                           extra={'id':entity_id,'stats':plan['stats'],'initial_allocation':plan})
        spec['moves']=[move_id];spec.pop('pos',None);spec['location']=deepcopy(glyph['location'])
        pokemon=Combatant(se.r,spec);se.gm.add_combatant(pokemon,side=a.side,reason='actual Sentry Runes activation')
        power=G._source(pokemon,'sentry:'+entity_id,'feature',owner_id=a.entity_id,rule_id=SENTRY,lifetime='permanent',tutor_points=0)
        if move_id==HP:pokemon.spec['hidden_power_type']=_power_type(a,move_id)
        else:power['hidden_power_types']={move_id:_power_type(a,move_id)}
        row=_glyph(se,a,glyph_id);row['status']='sentry';row['channeling']=False
        record=dict(id='sentry:'+entity_id,kind='sentry',location=deepcopy(row['location']),creator_id=a.entity_id,
            actor_id=entity_id,glyph_id=glyph_id,creation_level=a.level,hidden_power_id=move_id,
            created_at=se.elapsed_seconds,created_in_encounter=se.encounter_active,status='active')
        SPECIAL.observe_batch(se,[row,record],reason='actual native Sentry creation')
        return {'sentry_id':record['id'],'actor_id':entity_id,'glyph_id':glyph_id,'command_required':False}
    return G.transition(e,actor,apply)


def sentry_attack(e,pokemon,target,targets,*,damage_class='특수',shape='burst'):
    W.require_actors(e,pokemon,target)
    rows=[r for r in getattr(e,'_physical_objects',{}).values() if r.get('kind')=='sentry' and r.get('actor_id')==pokemon.entity_id and r.get('status')=='active']
    if len(rows)!=1:raise ValueError('actual live Sentry actor required')
    SPECIAL.validate_record(e,rows[0]);owner=W.actor_index(e)[rows[0]['creator_id']]
    if shape!='burst' and not acquired(owner,WORDS):raise ValueError('Words of Power owner required')
    if damage_class!=e.r.move(rows[0]['hidden_power_id']).get('class') or shape not in ('burst','melee','ranged','cone'):raise ValueError('copied Sentry Hidden Power class and printed shape required')
    group=list(dict.fromkeys([target,*targets]));W.require_actors(e,*group)
    def apply(se,p,t,*others):
        with _using(se,p,rows[0]['hidden_power_id'],damage_class,shape):return se.use_move_on(p,t,rows[0]['hidden_power_id'],[t,*others])
    return G.transition(e,pokemon,apply,participants=tuple(group))


def alarms(actor):
    return _payload(actor,ALARM).get('rune_alarms',{}) if acquired(actor,ALARM) else {}


def alarm(e,actor,glyph_id,*,trigger,automatic=None,options=None):
    require(e,actor,ALARM);_glyph(e,actor,glyph_id);W._text(trigger,'explicit arbitrary Alarm trigger')
    if glyph_id in alarms(actor):raise ValueError('one live Alarm binding per Glyph')
    if automatic not in (None,'explosive','sentry'):raise ValueError('printed automatic Alarm action required')
    if automatic:require(e,actor,EXPLOSIVE if automatic=='explosive' else SENTRY)
    if options is not None and type(options)is not dict:raise ValueError('actual automatic action choices required')
    import temporary_ap as TEMP
    TEMP.preflight_binding(actor,1,'rune_master')
    def apply(se,a):
        _pay(se,a,ALARM)
        identity='alarm:'+a.entity_id+':'+glyph_id
        a.ap_account.charge(1,mode='bind',instance_id=identity,temporary_binding_owner='rune_master')
        row={'id':identity,'glyph_id':glyph_id,'trigger':trigger,'automatic':automatic,'options':deepcopy(options or {}),
             'triggered':False,'observation':None,'at':se.elapsed_seconds}
        _payload(a,ALARM).setdefault('rune_alarms',{})[glyph_id]=row
        return deepcopy(row)
    return G.transition(e,actor,apply)


def binding(e,actor,identity):
    matches=[r for r in alarms(actor).values() if r['id']==identity]
    if len(matches)!=1 or actor.spec.get('ap_bound',{}).get(identity)!=1:raise ValueError('actual Rune Alarm exact AP binding required')
    _glyph(e,actor,matches[0]['glyph_id'],active=False)
    return matches[0]


def stop_alarm(e,actor,glyph_id):
    require(e,actor,ALARM)
    return G.transition(e,actor,lambda se,a:_stop_alarm(se,a,glyph_id,automatic=False))


def _stop_alarm(e,actor,glyph_id,*,automatic):
    row=alarms(actor).get(glyph_id)
    if row is None:return False
    binding(e,actor,row['id'])
    if not automatic:_pay(e,actor,ALARM,action='free')
    actor.ap_account.release_binding(row['id'],expected_amount=1)
    del alarms(actor)[glyph_id]
    return True


def end_binding(e,actor,row):
    return _stop_alarm(e,actor,row['glyph_id'],automatic=True)


def expire_glyph_bindings(e,glyph_id):
    glyph=getattr(e,'_physical_objects',{}).get(glyph_id,{})
    actor=W.actor_index(e).get(glyph.get('creator_id'))
    if actor is not None:return _stop_alarm(e,actor,glyph_id,automatic=True)
    return False


def before_revoke(e,actor,sources):
    # The existing grant source and ordinary AP account remain authoritative.
    for sid in sources:
        row=actor.spec.get(G.KEY,{}).get('sources',{}).get(sid,{})
        for gid in list(row.get('rune_alarms',{})):_stop_alarm(e,actor,gid,automatic=True)


def _automatic(e,actor,glyph_id,kind):
    frame=getattr(e,'_rune_alarm_trigger',None)
    return bool(frame and frame==(actor.entity_id,glyph_id,kind))


def observe_alarm(e,actor,glyph_id,*,fulfilled,distance_m,gm_id,reason):
    require(e,actor,ALARM);glyph=_glyph(e,actor,glyph_id)
    row=alarms(actor).get(glyph_id)
    if row is None:raise ValueError('actual sustained Alarm binding required')
    binding(e,actor,row['id'])
    if type(fulfilled)is not bool:raise ValueError('explicit GM trigger truth observation required')
    if type(distance_m)not in (int,float) or not 0<=distance_m< float('inf'):raise ValueError('actual finite trigger distance required')
    W._text(gm_id,'actual GM observer');W._text(reason,'actual Alarm trigger reason')
    def apply(se,a,*participants):
        actual=alarms(a)[glyph_id];actual['triggered']=fulfilled and distance_m<=30
        actual['observation']={'fulfilled':fulfilled,'distance_m':distance_m,'gm_id':gm_id,'reason':reason,'at':se.elapsed_seconds,'round':se.round_no}
        if not actual['triggered']:return {'triggered':False,'automatic':None}
        _glyph(se,a,glyph_id)['visible']=True
        se.log('Alarm Rune squawks: '+actual['trigger'],ALARM)
        result={'triggered':True,'visible':True,'audible_warning':True,'mental_warning_to':a.entity_id,'automatic':None}
        kind=actual['automatic']
        if not kind:return result
        scope=[a.spec.get('frequency_state',{}).get('scene',0),se.round_no]
        payload=_payload(a,ALARM)
        if kind=='explosive' and payload.get('alarm_explosive_round')==scope:return dict(result,waiting='one_explosive_glyph_per_round')
        if kind=='sentry' and any(r.get('kind')=='sentry' and r.get('creator_id')==a.entity_id and r.get('status')=='active' for r in getattr(se,'_physical_objects',{}).values()):return dict(result,waiting='one_active_sentry')
        options=deepcopy(actual['options']);index=W.actor_index(se)
        se._rune_alarm_trigger=(a.entity_id,glyph_id,kind)
        try:
            if kind=='explosive':
                target=index[options.pop('target_id')];targets=[index[uid] for uid in options.pop('target_ids')]
                result['automatic']=explosive(se,a,glyph_id,target,targets,automatic=True,**options)
                payload['alarm_explosive_round']=scope
            else:result['automatic']=sentry(se,a,glyph_id,automatic=True,**options)
        finally:del se._rune_alarm_trigger
        return result
    return G.transition(e,actor,apply,participants=tuple(p for p in W.actor_index(e).values() if p is not actor))


def glyph_view(e,actor,glyph_id):
    row=_glyph(e,actor,glyph_id,active=False)
    until=_payload(actor,EXPLOSIVE).get('glyph_glow',{}).get(glyph_id) if acquired(actor,EXPLOSIVE) else None
    return {'glyph':deepcopy(row),'glowing':until is not None and e.elapsed_seconds<until,
            'glow_until':until,'alarm':deepcopy(alarms(actor).get(glyph_id))}

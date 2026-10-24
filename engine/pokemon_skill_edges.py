"""Actual Skill Improvement investments and permanent-effect refunds.

The skill pool is permanent sheet state. Temporary pushed dice and ordinary
flat roll modifiers do not cause refunds. Receipts keep the spent point and
selected skill after an investment ends, so replay cannot pay it twice.
"""
from copy import deepcopy
import skill_modifiers as S
import state_fields as F
from pokemon_skill_profiles import pool,expression

SOURCE='poke_edge/스킬-향상'


def active(spec):
    return [r for r in spec.get('learned_poke_edges',[]) if r.get('source')==SOURCE and r.get('status','active')=='active']


def skill_pool(rules,spec,sid):
    from types import SimpleNamespace
    entries=[]
    for key,value in spec.get('skills',{}).items():
        if S.skill_id(rules.skill_policy,key)!=sid:continue
        try:parsed=pool(value)
        except ValueError:parsed=(S.rank(rules,SimpleNamespace(kind='pokemon',spec={'skills':{key:value}}),sid)[2],0)
        entries.append((key,parsed))
    if not entries or len({value for _,value in entries})!=1:raise ValueError('one actual permanent skill pool required for Skill Improvement')
    return entries[0][1]


def set_pool(rules,spec,sid,rank,flat):
    for key in list(spec.get('skills',{})):
        if S.skill_id(rules.skill_policy,key)==sid:spec['skills'].pop(key)
    spec.setdefault('skills',{})[sid]=expression(rank,flat)


def validate(rules,spec):
    rows=spec.get('learned_poke_edges',[])
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Poke Edge investments must be records')
    selected=set()
    for row in rows:
        if row.get('source')!=SOURCE:continue
        import poke_edge_variants as VARIANTS
        VARIANTS.validate_receipt(rules,row,history=True)
        if spec.get('kind')!='pokemon':raise ValueError('Skill Improvement investment requires an actual Pokemon')
        if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Skill Improvement source needs its own policy')
        sid=S.skill_id(rules.skill_policy,row.get('skill'),required=True)
        if sid!=row['skill']:raise ValueError('canonical invested skill required')
        lesson=bool(row.get('mentor_source_id'))
        if lesson:__import__('mentor').validate_edge_origin(rules,row)
        F.integer(row.get('point_cost'),'Skill Improvement investment',0 if lesson else 1,0 if lesson else 1)
        F.integer(row.get('rank_before'),'skill rank before investment',1)
        status=row.get('status','active')
        if status not in ('active','refunded'):raise ValueError('invalid Skill Improvement lifecycle')
        if status=='active':
            if sid in selected:raise ValueError('one active Skill Improvement per distinct skill')
            selected.add(sid);rank,_=skill_pool(rules,spec,sid)
            if rank>6:raise ValueError('permanent Skill Improvement overflow requires actual refund')
        else:
            refund=row.get('refund',{})
            if not isinstance(refund,dict) or refund.get('source')!=SOURCE or not refund.get('reason'):raise ValueError('ended Skill Improvement needs its actual refund receipt')
            F.integer(refund.get('points'),'refunded Skill Improvement points',0 if lesson else 1,1)


def refund_excess(rules,spec,*,reason):
    """Run on a staged permanent change, before native state is committed."""
    ended=[]
    for row in active(spec):
        if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Skill Improvement source needs its own refund policy')
        F.integer(row.get('point_cost'),'refundable Skill Improvement investment',0 if row.get('mentor_source_id') else 1,1)
        sid=S.skill_id(rules.skill_policy,row['skill'],required=True)
        rank,flat=skill_pool(rules,spec,sid)
        if rank<=6:continue
        F.integer(spec.get('tutor_points'),'actual Tutor Point balance for refund',0)
        set_pool(rules,spec,sid,rank-1,flat)
        amount=__import__('mentor').refund_edge_spec(rules,spec,row,reason) if row.get('mentor_source_id') else 1
        if not row.get('mentor_source_id'):spec['tutor_points']+=amount
        row.update(status='refunded',refund={'source':SOURCE,'points':amount,'reason':reason,
                                            'permanent_rank_before_refund':rank,'permanent_rank_after_refund':rank-1})
        ended.append(sid)
    validate(rules,spec)
    return ended


def lesson_acquire(engine,teacher,pupil,skill,source_id):
    """Apply the native skill contribution; the lesson owns prerequisites and payment."""
    validate(engine.r,pupil.spec)
    sid=S.skill_id(engine.r.skill_policy,skill,required=True)
    if any(row['skill']==sid for row in active(pupil.spec)):
        raise ValueError('Skill Improvement requires a different skill on each acquisition')
    rank,flat=skill_pool(engine.r,pupil.spec,sid)
    if rank>=6:raise ValueError('Skill Improvement cannot exceed permanent Master rank')
    set_pool(engine.r,pupil.spec,sid,rank+1,flat)
    row={'source':SOURCE,'status':'active','trainer_id':teacher.entity_id,'skill':sid,'rank_before':rank,
         'point_cost':0,'training_source':'feat/수업','completed_at':engine.elapsed_seconds,
         'acquired_level':pupil.level,'mentor_source_id':source_id}
    pupil.spec.setdefault('learned_poke_edges',[]).append(row)
    return row


def species_change(rules,spec,old_species,new_species):
    """Retain the individual investment and differences from the old Dex pool."""
    for row in active(spec):
        sid=row['skill'];rank,flat=skill_pool(rules,spec,sid)
        # GM template pools have their own explicit evolution choice producer.
        template=spec.get('pokemon_skill_profile',{})
        if sid in template.get('assigned_pools',{}):continue
        values=[]
        for species in (old_species,new_species):
            matches=[v for k,v in rules.species_skills.get(species['name'],{}).items() if S.skill_id(rules.skill_policy,k)==sid]
            if len(matches)!=1:raise ValueError('evolution needs both species skill sources for invested skill')
            value=matches[0];values.append((value['rank'],int(str(value.get('mod','+0')))))
        set_pool(rules,spec,sid,rank+values[1][0]-values[0][0],flat+values[1][1]-values[0][1])
    return refund_excess(rules,spec,reason='actual evolution: '+old_species['id']+' -> '+new_species['id'])

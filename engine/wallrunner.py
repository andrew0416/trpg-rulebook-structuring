"""Wallrunner supplies an observed surface approach to the native jump."""
from copy import copy,deepcopy
from pathlib import Path
import json
import acquisition_qualification as Q,skill_modifiers as S,movement_actions as M
import common_checks as C,world_entities as W
from source_context import verified_source

SOURCE='edge/벽달리기'
NAMES=(SOURCE,'벽달리기','Wallrunner')

def policy(rules):
    value=json.loads((Path(rules.root)/'data/wallrunner-policy.json').read_text(encoding='utf-8'))
    if value['rule_id']!=SOURCE or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected native Wallrunner source required')
    verified_source(rules,value['source'],label='Wallrunner')
    verified_source(rules,value['csv_source'],label='Wallrunner duplicate CSV')
    source=rules.selection.units[SOURCE]['source']
    if source.get('file')!=value['source']['file'].removeprefix('input/') or source.get('lines')!=value['lines']:raise ValueError('Wallrunner literal source identity changed')
    return value

def validate(actor):
    entries=actor.spec.get('edges',[])
    if type(entries) not in (list,tuple):raise ValueError('actual acquired Edge list required')
    if not any(value in NAMES for value in entries):return False
    return Q.owned_skill_edge(actor,SOURCE,policy(actor.r),prerequisite_reason='Wallrunner requires Expert Acrobatics')

def prepare(engine,actor,declaration,inflight):
    W.require_actors(engine,actor)
    if type(declaration) is not dict or set(declaration)!={'path','vertical_surface','reason'}:raise ValueError('exact actual Wallrunner path, vertical surface and reason required')
    M.reason(declaration['reason'])
    previous=(inflight or {}).get('basis',{}).get('wall_run')
    if previous:
        if previous['declaration']!=declaration:raise ValueError('cannot change an already observed Wallrunner approach')
        progress=inflight.get('wall_progress')
        if progress is not None:
            M._paid_receipts(engine,progress);M._paid_progress(actor,previous['path'][1:],progress)
        elif actor.pos!=previous['path'][-1]['position'] or actor.spec.get('_movement_altitude',0)!=previous['path'][-1]['altitude']:raise ValueError('cannot change an already observed Wallrunner approach')
        return deepcopy(previous)
    if not validate(actor):raise ValueError('actual acquired Wallrunner required')
    if declaration['vertical_surface'] is not True:return C.PendingDecision('GM observation that the complete actual path follows a vertical surface')
    result=M.observed_path(engine,actor,declaration['path'])
    maximum=S.effective_rank(actor.r,actor,policy(actor.r)['skill'])
    if result['distance']>maximum:raise ValueError('Wallrunner path exceeds Acrobatics rank metres')
    return dict(result,source=SOURCE,maximum=maximum,declaration=deepcopy(declaration))

def launch(actor,plan):
    result=copy(actor);result.spec=dict(actor.spec)
    result.pos=plan['path'][-1]['position'];result.spec['_movement_altitude']=plan['path'][-1]['altitude']
    return result

def traverse(engine,actor,plan,*,progress=None):
    progress={} if progress is None else progress
    path=plan['path'][1:]
    M._paid_receipts(engine,progress);M._paid_progress(actor,path,progress)
    if progress['phase']=='complete':return True
    for node in path[progress['next']:]:
        def validate():
            segment=[dict(position=actor.pos,altitude=actor.spec.get('_movement_altitude',0)),
                     {key:value for key,value in node.items() if key!='diagonals'}]
            return M.observed_path(engine,actor,segment)
        validate()
        if not M._paid_departure(engine,actor,node['position'],node['altitude'],progress):return False
        validate()
        actor.pos=node['position'];actor.spec['_movement_altitude']=node['altitude'];actor.airborne=node['altitude']>0
        actor._diagonal_steps=node['diagonals']
        progress.update(next=progress['next']+1,position=actor.pos,altitude=node['altitude'],diagonals=actor._diagonal_steps,phase='entering')
        if not M._paid_entry(engine,actor,progress,surface=node['altitude']==0):return False
    progress['phase']='complete'
    engine.log('  '+actor.name+': Wallrunner '+str(plan['distance'])+'m to actual jump origin',SOURCE)
    return True

def run_jump(engine,actor,destination,options):
    """Commit observed skill choices; roll back errors before observation."""
    import state_grants as G,jump_actions as J,skill_feature_actions as SF
    caught={}
    def apply(staged,current):
        try:return J.jump(staged,current,destination,**options,_wall_staged=True)
        except Exception as error:
            keys=('jump:'+current.spec['id']+':'+options['jump_id'],
                  'fall:'+current.spec['id']+':jump-fall:'+options['jump_id'])
            pending_fall=current.spec.get('_jump_attempts',{}).get(options['jump_id'],{}).get('fall_pending') is True
            for key in keys:
                run=getattr(staged,'_skill_sequences',{}).get(key)
                if run and (not run['closed'] or pending_fall) and any(SF.event(staged,owner,uid) is not None for owner,request,feature,uid in run['requests']):
                    caught['error']=error
                    return None
            raise
    result=G.transition(engine,actor,apply)
    if caught:raise caught['error']
    return result

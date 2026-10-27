"""Source-bound Survivalist check effects, separate from generic arithmetic.
GM records actual terrain/light. Terrain Talents work in every terrain.
Unrelated movement/immunity/damage clauses in the same table are not claimed.
"""
from copy import deepcopy
import common_checks as C
import skill_modifiers as S
import contest_features as F
SURVIVALIST='class/생존가'
TALENT='feat/지형-재능'
CLASS_SOURCE='ch04-trainer-classes/프로페셔널-클래스/생존가'
TERRAIN_SOURCE=CLASS_SOURCE
TERRAINS=('grassland','forest','wetland','ocean','tundra','mountain','cave','urban','desert')
ALIASES=dict(zip(('초원','숲','습지','바다','툰드라','산','동굴','도시','사막'),TERRAINS))
FIVE={'athletics','acrobatics','stealth','perception','survival'}
CHILDREN={'feat/내추럴-파이터':3,'feat/트래퍼':4,'feat/야생-가이드':5}
PURPOSES={'distant_object','climb','balance','maintain_footing','resist_push','resist_trip','push','trip'}
PLAINS='C2CSV/input/db/class-data.csv:R25:technique'
NIGHT_PROVENANCE='observed-terrain-v1'
def text(v,label):
 if not isinstance(v,str) or not v.strip():raise ValueError('nonempty '+label+' required')
 return v
def terrain(v):
 v=ALIASES.get(v,v)
 if v not in TERRAINS:raise ValueError('known Survivalist terrain required')
 return v
def source(e,uid):
 if e.r._selected_rule(uid)!=uid:raise ValueError('selected Survivalist variant needs sourced policy')
def base(e,a):
 F.conscious_trainer(a);F.require(e,a,SURVIVALIST);source(e,CLASS_SOURCE)
 if S.rank(e.r,a,'생존')[2]<3:raise ValueError('Survivalist requires Novice Survival')
def feature_count(e,a):
 base(e,a);count=1;skill=S.rank(e.r,a,'생존')[2]
 for uid,minimum in CHILDREN.items():
  if F.owned(a,uid):
   F.require(e,a,uid)
   if skill<minimum:raise ValueError('Survivalist feature skill prerequisite not met')
   count+=1
 if F.owned(a,TALENT):
  F.require(e,a,TALENT);rank=a.spec.get('feat_ranks',{}).get(TALENT);C.integer(rank,'Terrain Talent acquired rank',1,2);count+=rank
 if F.owned(a,'feat/지리-적응'):
  F.require(e,a,'feat/지리-적응')
  if skill<6 or count<4:raise ValueError('Adaptive Geography requires four other Survivalist features and Master Survival')
  count+=1
 return count

def current_environment(e,a):
 """A known current cell outranks a scene-wide GM terrain observation."""
 env=a.spec.get('_survivalist_environment')
 if e.grid is not None and a.location['kind']=='grid':
  key=','.join(map(str,a.pos));mapping=getattr(e.grid,'terrain_types',{})
  if key in mapping:
   observation=getattr(e.grid,'terrain_observations',{}).get(key,{})
   return {'terrains':tuple(mapping[key]),'source':'observed_cell','position':list(a.pos),
           'reason':observation.get('reason'),'observed_seconds':e.elapsed_seconds}
 if env is None:return None
 return dict(deepcopy(env),source='explicit_gm_environment')

def position_changed(e,a,*,event):
 """Keep the first observed departure even if the actor later returns."""
 opened=a.spec.get('_survivalist_open_night')
 if not opened or opened.get('left_terrain'):return
 env=current_environment(e,a)
 if env is not None and opened['terrain'] not in env['terrains']:
  opened['left_terrain']=True
  opened['departure']={'event':event,'seconds':e.elapsed_seconds,'environment':deepcopy(env)}

def verified_night(e,a,n):
 # Legacy records retain their bytes, but cannot prove an unrecorded location history.
 if not isinstance(n,dict) or n.get('source')!=CLASS_SOURCE or n.get('provenance')!=NIGHT_PROVENANCE or n.get('owner_id')!=a.entity_id:return False
 if n.get('left_terrain') or n.get('end_seconds',-1)<=n.get('start_seconds',-1) or n['end_seconds']>e.elapsed_seconds:return False
 return all(isinstance(n.get(key),dict) and n['terrain'] in n[key].get('terrains',[]) for key in ('start_environment','end_environment'))
def selected(e,a):
 if CSV_STATE in a.spec:return csv_selected(e,a)
 base(e,a);records=a.spec.get('_survivalist_terrains',[]);values=[]
 if not isinstance(records,list):raise ValueError('actual acquired terrain records required')
 for r in records:
  if not isinstance(r,dict) or r.get('source')!=SURVIVALIST:raise ValueError('terrain selection provenance missing')
  value=terrain(r['terrain']);nights=r.get('nights',[])
  if len(nights)<3 or len(set(nights))!=len(nights):raise ValueError('three distinct completed nights required')
  actual=a.spec.get('_survivalist_nights',{})
  for identity in nights:
   n=actual.get(identity)
   if not verified_night(e,a,n) or n['terrain']!=value:raise ValueError('verified actual completed nights required; legacy history needs explicit historical correction')
  if r.get('completed_seconds',-1)>e.elapsed_seconds:raise ValueError('terrain selection is from the future')
  values.append(value)
 if len(set(values))!=len(values):raise ValueError('selected terrains must be distinct')
 count=feature_count(e,a);maximum=1+int(count>=2)+int(count>=4)+int(count>=6)
 if len(values)>maximum:raise ValueError('acquired features do not allow this many terrains')
 return tuple(values)
def observe_environment(e,a,*,terrains,light,reason):
 if not isinstance(terrains,(tuple,list)):raise ValueError('explicit current terrain list required')
 values=tuple(terrain(t) for t in terrains)
 if len(set(values))!=len(values):raise ValueError('duplicate current terrain')
 if light not in ('normal','low_light','complete_darkness'):raise ValueError('explicit current light level required')
 text(reason,'GM environment reason')
 a.spec['_survivalist_environment']={'terrains':values,'light':light,'reason':reason,'observed_seconds':e.elapsed_seconds}
 position_changed(e,a,event='GM environment observation')
 return deepcopy(a.spec['_survivalist_environment'])
def begin_night(e,a,*,night_id,terrain_name,reason):
 text(night_id,'night identity');text(reason,'GM overnight reason');value=terrain(terrain_name)
 if e.encounter_active:raise ValueError('overnight interval cannot begin during combat')
 env=current_environment(e,a)
 if not env or value not in env['terrains']:raise ValueError('overnight terrain must match current environment')
 if night_id in a.spec.get('_survivalist_nights',{}) or a.spec.get('_survivalist_open_night') is not None:raise ValueError('duplicate or overlapping overnight interval')
 a.spec['_survivalist_open_night']={'id':night_id,'terrain':value,'start_seconds':e.elapsed_seconds,'reason':reason,
   'source':CLASS_SOURCE,'provenance':NIGHT_PROVENANCE,'owner_id':a.entity_id,'start_environment':deepcopy(env)}
def finish_night(e,a,*,night_id,reason):
 text(reason,'GM completed overnight reason');opened=a.spec.get('_survivalist_open_night')
 if not opened or opened['id']!=night_id:raise ValueError('same actual overnight interval required')
 if opened.get('provenance')!=NIGHT_PROVENANCE or opened.get('source')!=CLASS_SOURCE or opened.get('owner_id')!=a.entity_id:raise ValueError('verified overnight beginning required; legacy history needs explicit historical correction')
 if opened.get('left_terrain'):raise ValueError('overnight stay was interrupted by leaving its terrain')
 env=current_environment(e,a)
 if not env or opened['terrain'] not in env['terrains']:raise ValueError('completed overnight terrain must still match')
 if e.encounter_active or e.elapsed_seconds<=opened['start_seconds']:raise ValueError('positive completed noncombat overnight interval required')
 r={**opened,'end_seconds':e.elapsed_seconds,'completion_reason':reason,'end_environment':deepcopy(env)}
 a.spec.setdefault('_survivalist_nights',{})[night_id]=r;del a.spec['_survivalist_open_night'];return deepcopy(r)
def select_terrain(e,a,*,terrain_name,minutes,reason):
 import action_lifecycle as ACTION
 base(e,a);value=terrain(terrain_name);old=selected(e,a)
 C.integer(minutes,'GM Extended Action minutes',1);text(reason,'GM Extended Action reason')
 if e.encounter_active:raise ValueError('terrain selection requires noncombat Extended Action')
 if value in old:raise ValueError('terrain already selected')
 count=feature_count(e,a);maximum=1+int(count>=2)+int(count>=4)+int(count>=6)
 if len(old)>=maximum:raise ValueError('next terrain requires two, four or six acquired features')
 nights=[i for i,n in a.spec.get('_survivalist_nights',{}).items() if verified_night(e,a,n) and n['terrain']==value]
 if len(nights)<3:raise ValueError('terrain requires at least three actual completed nights')
 if not ACTION.status_permission(e,a,'extended'):raise ValueError('Extended Action permission unavailable')
 e.advance_time(minutes*60,[a]);ACTION.record_action(e,a,'extended')
 r={'source':SURVIVALIST,'terrain':value,'nights':tuple(nights),'minutes':minutes,'reason':reason,'completed_seconds':e.elapsed_seconds,'feature_count':count}
 a.spec.setdefault('_survivalist_terrains',[]).append(r);return deepcopy(r)
def choose_talents(e,a,*,terrains):
 available=selected(e,a);F.require(e,a,TALENT);source(e,TERRAIN_SOURCE)
 rank=a.spec.get('feat_ranks',{}).get(TALENT);C.integer(rank,'Terrain Talent acquired rank',1,2)
 if len(available)<rank*2:raise ValueError('Terrain Talent requires two/four mastered terrains')
 if not isinstance(terrains,(list,tuple)):raise ValueError('actual selected talent terrains required')
 values=tuple(terrain(t) for t in terrains)
 if len(values)!=rank*2 or len(set(values))!=len(values) or not set(values)<=set(available):raise ValueError('two distinct mastered-terrain talents per acquired rank required')
 previous=a.spec.get('_survivalist_talents')
 if previous is not None and (previous['rank']>=rank or not set(previous['terrains'])<=set(values)):raise ValueError('acquired talent choices cannot be rewritten')
 a.spec['_survivalist_talents']={'source':TALENT,'rank':rank,'terrains':values,'selected_seconds':e.elapsed_seconds};return values
def talents(e,a):
 if not F.owned(a,TALENT):
  if '_survivalist_talents' in a.spec:raise ValueError('talent record requires actual acquired feature')
  return ()
 if CSV_STATE in a.spec:
  values=_csv_talent_values(e,a)
  return () if a.spec[CSV_STATE]['active'] is None else values
 available=selected(e,a);F.require(e,a,TALENT);source(e,TERRAIN_SOURCE)
 r=a.spec.get('_survivalist_talents');rank=a.spec.get('feat_ranks',{}).get(TALENT);C.integer(rank,'Terrain Talent acquired rank',1,2)
 if not r or r.get('source')!=TALENT or r.get('rank')!=rank:raise ValueError('actual chosen Terrain Talents required')
 values=r['terrains']
 if len(values)!=rank*2 or len(set(values))!=len(values) or not set(values)<=set(available):raise ValueError('talent selection prerequisites no longer established')
 return tuple(values)
def modifier(e,a,skill,context=None):
 if context is not None:
  from blessing_skill_features import PURPOSES as BLESSING_PURPOSES
  import telekinetic_combat as TK
  if isinstance(context,dict) and context.get('purpose')==TK.PURPOSE:
   TK.roll_bonus(e,a,skill,context)
  elif not isinstance(context,dict) or set(context)!={'purpose','reason'} or context['purpose'] not in PURPOSES|BLESSING_PURPOSES|{'telekinetic_carry','resist_grapple','resist_disarm','glitch_phenomenon','capability/추적자','pokemon_obedience'}:raise ValueError('known GM skill purpose and reason required')
  text(context['reason'],'GM skill context reason')
 if not F.owned(a,SURVIVALIST):
  if any(k in a.spec for k in ('_survivalist_terrains','_survivalist_talents')):raise ValueError('Survivalist records require actual class')
  return ()
 choices=selected(e,a);traits=talents(e,a);env=current_environment(e,a)
 if choices and env is None:raise ValueError('GM current environment required for acquired terrain bonus')
 skill_id=S.skill_id(e.r.skill_policy,skill);sources=[]
 if skill_id in FIVE and env:
  import survivalist_class as CLASS_RULES
  matching=set(choices)&set(CLASS_RULES.effective_terrains(e,a,env['terrains']))
  if matching:sources.append((SURVIVALIST,2,tuple(sorted(matching))))
 if context is not None:
  purpose=context['purpose']
  if 'grassland' in traits and purpose=='distant_object' and skill_id=='perception':
   import static_trainer_modifiers as STATIC
   STATIC._clause(e.r,'C2CSV/input/db/class-data.csv:R25:technique')
   sources.append((TALENT,2,'Plains Runner: '+context['reason']))
  if 'mountain' in traits and purpose in {'climb','balance','maintain_footing','resist_push','resist_trip'}:sources.append((TALENT,2,'Surefooted: '+context['reason']))
 return tuple(sources)


def movement(e,a,values):
 """Project the selected Plains Runner talent into native land movement; class rounds and Deep Diver follow."""
 result=dict(values)
 chosen=talents(e,a) if F.owned(a,SURVIVALIST) else ()
 if 'grassland' in chosen:
  import static_trainer_modifiers as STATIC
  STATIC._clause(e.r,'C2CSV/input/db/class-data.csv:R25:technique')
  C.integer(result.get('land'),'actual land movement',0)
  result['land']+=2
 import survivalist_class as CLASS_RULES
 return CLASS_RULES.movement(e,a,result,talents=chosen)

def fall_adjustment(e,a,damage_distance,height_injuries):
 """Return Mountain terrain talent's exact falling projections."""
 if not F.owned(a,SURVIVALIST) or 'mountain' not in talents(e,a):
  return damage_distance,height_injuries,0,0
 import static_trainer_modifiers as STATIC
 STATIC._clause(e.r,'C2CSV/input/db/class-data.csv:R30:technique')
 C.integer(damage_distance,'actual falling damage distance',0)
 C.integer(height_injuries,'actual falling height injuries',0)
 return max(0,damage_distance-1),max(0,height_injuries-1),min(1,damage_distance),min(1,height_injuries)
def vision(e,a):
 import capability_traits as TRAITS
 senses=TRAITS.projection(a,engine=e)
 if senses['blindsense']:return 'none',False
 import vision_impairment as VISION
 afflicted=VISION.explicit_level(a)
 if afflicted!='none':return afflicted,False
 traits=talents(e,a) if F.owned(a,SURVIVALIST) else ();env=a.spec.get('_survivalist_environment',{'light':'normal'});light=env['light'];cave='cave' in traits
 if light in ('low_light','complete_darkness') and senses['darkvision']:light='normal'
 if light=='low_light' and __import__('survivalist_class').low_light_sight(e,a):light='normal'
 if light=='complete_darkness':return ('ordinary',True) if cave else ('total',False)
 if light=='low_light' and not cave:return 'ordinary',False
 return 'none',False

def blinded_plan(e,a,options=None,*,allow_total=False):
 options={} if options is None else dict(options);level,substitution=vision(e,a)
 if level=='total' and not allow_total:raise ValueError('Total Blindness requires the relative movement adapter')
 if level=='none':
  if options:raise ValueError('blinded traversal options require actual Blindness')
  return None
 skill=options.pop('skill','곡예');identity=S.skill_id(e.r.skill_policy,skill,required=True)
 if identity not in ({'acrobatics','survival'} if substitution else {'acrobatics'}):raise ValueError('Cave Dweller substitutes only darkness-induced avoid-Tripped check')
 source(e,'condition/실명');import skill_feature_actions as SF
 prepared=SF.prepared_for_sequence(e,a,skill,options) if options.get('feature') else e._prepare_skill_roll(a,skill,**options)
 if prepared[3] is not None:options['fixed']=prepared[3]
 return skill,options


def approach_preflight(e,a,target,reach,movement_mode,options):
 """Validate optional vision inputs before the ordinary Shift is spent."""
 old=a.spec.get('_survivalist_shift')
 if old is not None:
  if old['finished']:return False
  identity=(target.spec.get('id',target.name),tuple(target.pos),reach,movement_mode)
  if old['target']!=identity:raise ValueError('cannot replace an observed blinded Shift declaration')
  continue_approach(e,a,target,options)
  return True
 level,_=vision(e,a)
 if level=='none':
  if options is not None:raise ValueError('blinded traversal declaration requires actual Blindness')
  return False
 if level=='total':raise ValueError('Total Blindness requires relative movement and explicit Slowly/Quickly')
 if options is None:return False # Hold only if the actual chosen route enters hazardous terrain.
 _traversal_options(e,a,options)
 return False

def _traversal_options(e,a,options):
 if not isinstance(options,dict) or set(options)-{'movement_id','frequency','reason','check_options'}:raise ValueError('explicit blinded traversal options required')
 text(options.get('movement_id'),'blinded movement identity');text(options.get('reason'),'GM check frequency reason')
 if options.get('frequency') not in ('once_per_shift','each_hazard_cell'):raise ValueError('GM must settle unspecified blinded-check repetition')
 checks=options.get('check_options',[])
 if not isinstance(checks,(list,tuple)) or not checks:raise ValueError('one source-bound option record per actual check required')
 plans=[blinded_plan(e,a,x) for x in checks]
 if any(x is None for x in plans):raise ValueError('actual Blindness required for traversal checks')
 return plans

def prepare_approach(e,a,target,reach,movement_mode,mode,budget,path,options):
 """Validate the actual selected path before paying its native Shift."""
 level,_=vision(e,a)
 if level=='none':return False
 selected_path=[];spent=0;previous=tuple(a.pos);parity=getattr(a,'_diagonal_steps',0)%2
 for state in path:
  q=tuple(state[:2]);diagonal=previous[0]!=q[0] and previous[1]!=q[1]
  import movement_actions as MOVEMENT
  if max(abs(previous[0]-q[0]),abs(previous[1]-q[1]))==1:
   step,next_diagonals=MOVEMENT.step_cost(previous,q,parity)
  else:
   # Preserve this adapter's existing zero/nonadjacent observation contract.
   step=2 if diagonal and parity else 1;next_diagonals=parity+int(diagonal)
  cost=step+MOVEMENT.slow_terrain_penalty(e,a,q,mode,step=step)
  if spent+cost>budget:break
  selected_path.append((q,cost,diagonal));spent+=cost;parity=next_diagonals%2;previous=q
 hazards=[i for i,(q,_,_) in enumerate(selected_path) if (q in e.grid.rough or q in e.grid.slow) and not MOVEMENT.ordinary_terrain(e,a,q,movement=True)]
 if not hazards:return False
 plans=_traversal_options(e,a,options)
 indices=hazards[:1] if options['frequency']=='once_per_shift' else hazards
 if len(plans)!=len(indices):raise ValueError('one option record per actual blinded traversal check required')
 identities=[opts.get('roll_id') for _,opts in plans if opts.get('feature') is not None]
 if len(set(identities))!=len(identities):raise ValueError('each blinded traversal check needs distinct roll identity')
 previous=a.spec.get('_survivalist_shift')
 if previous and previous.get('movement_id')==options['movement_id']:raise ValueError('blinded movement identity already used')
 record={'movement_id':options['movement_id'],'target':(target.spec.get('id',target.name),tuple(target.pos),reach,movement_mode),
         'path':selected_path,'next_index':0,'check_indices':indices,'frequency':options['frequency'],'reason':options['reason'],
         'origin':tuple(a.pos),'mode':mode,'budget':budget,'moved':0,'spent':0,'finished':False,
         'checks':[]}
 return record

def begin_approach(e,a,target,record,options):
 a.spec['_survivalist_shift']=record
 return continue_approach(e,a,target,options)

def continue_approach(e,a,target,options):
 import skill_feature_actions as SF
 import turn as TURN
 import movement_actions as MOVEMENT
 r=a.spec['_survivalist_shift']
 progress=r.setdefault('entry_progress',{'effects':[],'phase':'ready'})
 MOVEMENT._paid_receipts(e,progress)
 expected=r['origin'] if r['next_index']==0 else tuple(r['path'][r['next_index']-1][0])
 if tuple(a.pos)!=expected:raise ValueError('actor moved while blinded Shift observation is pending')
 if not TURN.can_act(e,a) or not TURN.movement_permission(e,a):raise ValueError('pending blinded Shift no longer has movement permission')
 if not isinstance(options,dict) or any(options.get(k)!=r[k] for k in ('movement_id','frequency','reason')):raise ValueError('cannot change an observed blinded Shift policy')
 plans=_traversal_options(e,a,options)
 if len(plans)!=len(r['check_indices']):raise ValueError('cannot change blinded Shift check count')
 for index in range(r['next_index'],len(r['path'])):
  q,cost,diagonal=r['path'][index];passed=True
  if not e.grid.inside(q) or e.grid.blocked(a.pos,q) or q in e.occupied(a):raise ValueError('observed blinded Shift path changed before continuation')
  origin=a.pos;altitude=a.spec.get('_movement_altitude',0)
  if r.get('departure_index')!=index:
   if not MOVEMENT._paid_departure(e,a,q,altitude,progress):
    if progress['phase']=='reaction_pending':return deepcopy(r['checks'])
    break
   r['departure_index']=index
  if index in r['check_indices']:
   ordinal=r['check_indices'].index(index);skill,opts=plans[ordinal]
   basis={'origin':r['origin'],'path':r['path'],'check_cell':q,'source':'condition/실명','frequency':r['frequency'],'reason':r['reason']}
   if opts.get('feature') is not None:
    result=SF.sequence(e,'blind:'+r['movement_id']+':'+str(ordinal),basis,[(a,skill,opts)],lambda rolls:SF.resolve_check(e,a,skill,10,rolls[0],opts))
   else:
    result=SF.resolve_check(e,a,skill,10,e.skill_roll(a,skill,**opts),opts);SF.finish(e,a,opts.get('roll_id'))
   r=a.spec['_survivalist_shift'];progress=r['entry_progress'];r['checks'].append({'skill':skill,'result':result,'cell':q});passed=result.passed
  if a.pos!=origin or a.spec.get('_movement_altitude',0)!=altitude or not TURN.can_act(e,a) or not TURN.movement_permission(e,a):break
  if diagonal:a._diagonal_steps=getattr(a,'_diagonal_steps',0)+1
  a.pos=q;r['spent']+=cost;r['moved']+=1;r['next_index']=index+1
  import burrow_tunnels as TUNNELS
  TUNNELS.enter(e,a,r['mode'])
  MOVEMENT.entry_mode(a,r['mode'])
  import control_mount as MOUNT,living_weapon as LIVING
  MOUNT.sync(e,a);LIVING.sync(e,a)
  ready=MOVEMENT._paid_entry(e,a,progress,surface=True)
  if not passed:
   e.apply_status(a,'넘어짐');break
  if not ready:
   if progress['phase']=='entry_pending':return deepcopy(r['checks'])
   break
  if a.fainted or a.dead or '구속' in a.conditions or '넘어짐' in a.conditions:break
 r=a.spec['_survivalist_shift'];r['finished']=True
 e.log('  '+a.name+' 실명 이동: '+str(r['moved'])+'칸; '+str(a.pos),'condition/실명')
 return deepcopy(r['checks'])


def activity(e,a,activity,**options):
 import survivalist_class as CLASS_RULES
 handlers={'observe_environment':observe_environment,'begin_night':begin_night,'finish_night':finish_night,'select_terrain':select_terrain,'choose_talents':choose_talents,'select_csv_terrains':select_csv_terrains,'withdraw_csv_terrains':withdraw_csv_terrains,
  'create_trap_tool':CLASS_RULES.create_trap_tool,'deploy_trap_tool':CLASS_RULES.deploy_trap_tool,'wilderness_guide':CLASS_RULES.wilderness_guide,'adaptive_geography':CLASS_RULES.adaptive_geography}
 if activity not in handlers:raise ValueError('unknown Survivalist activity')
 return handlers[activity](e,a,**options)


# CSV daily selection is a separate printed contract.  In particular, it does
# not import the Markdown contract's three completed nights or append-only
# mastery procedure.  Both contracts project into the same skill and movement
# consumers above.
CSV_STATE='_survivalist_csv_selection'
CSV_POLICY='data/survivalist-csv-policy.json'
CSV_CLAUSES=('C2CSV/input/db/feats.csv:R376:main','C2CSV/input/db/feats.csv:R754:main')
CSV_FREQUENCY={'kind':'daily','uses':1}
CSV_QUOTA='survivalist-csv:daily-selection'


def csv_policy(rules):
 import csv,hashlib,json
 import resolution_transaction as FINGERPRINTS
 from pathlib import Path
 cached=getattr(rules,'_survivalist_csv_policy',None)
 if cached is not None:return cached
 data=json.loads((Path(rules.root)/CSV_POLICY).read_text(encoding='utf-8'))
 if data.get('schema_version')!=1 or set(data.get('clauses',{}))!=set(CSV_CLAUSES):raise ValueError('exact Survivalist CSV policy required')
 if data.get('acquisition_source')!=SURVIVALIST:raise ValueError('actual Survivalist acquisition source required')
 if set(data.get('source_files',{}))!={'input/db/feats.csv'}:raise ValueError('exact Survivalist CSV source file required')
 for clause_id,clause in data['clauses'].items():
  expected_record=int(clause_id.split(':R')[1].split(':')[0])
  if (clause.get('id')!=clause_id or clause.get('csv_record')!=expected_record
      or clause.get('file')!='input/db/feats.csv' or clause.get('columns')!=[1,2,3,4,5]
      or clause.get('name')!=clause.get('cells',[None])[0]):raise ValueError('Survivalist CSV record identity changed')
 for relative,digest in data['source_files'].items():
  path=Path(rules.root)/relative
  if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Survivalist CSV source file changed')
  with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
  for clause in data['clauses'].values():
   if clause['file']!=relative:continue
   cells=[rows[clause['csv_record']-1][column-1] for column in clause['columns']]
   cell_digest=FINGERPRINTS.json_fingerprint(cells, sort_keys=False, compact=True, allow_nan=True)
   if cells!=clause['cells'] or cell_digest!=clause['cell_sha256']:raise ValueError('Survivalist CSV clause changed')
 rules._survivalist_csv_policy=data
 return data


def _csv_token(a,sequence):
 return 'survivalist-csv:'+a.entity_id+':'+str(sequence)


def _csv_validate(e,a):
 import frequency as FREQUENCY
 import state_grants as GRANTS
 state=a.spec.get(CSV_STATE)
 if state is None:return
 policy=csv_policy(e.r)
 if (not isinstance(state,dict) or set(state)!={'owner_id','acquisition_source','history','active'}
     or a.kind!='trainer' or state['owner_id']!=a.entity_id or state['acquisition_source']!=SURVIVALIST):raise ValueError('Survivalist CSV owner/source identity changed')
 if F.owned(a,SURVIVALIST):F.require(e,a,SURVIVALIST);source(e,CLASS_SOURCE)
 if a.spec.get('_survivalist_terrains'):raise ValueError('CSV daily choice and Markdown terrain mastery cannot be mixed')
 history=state['history']
 if not isinstance(history,list) or not history:raise ValueError('Survivalist CSV needs actual selection history')
 FREQUENCY.validate(a)
 previous_end=-1;periods=[]
 for index,row in enumerate(history,1):
  required={'sequence','clause_id','cell_sha256','terrains','feature_count','started_seconds','completed_seconds','minutes','reason','frequency'}
  if not isinstance(row,dict) or set(row)-{'withdrawal'}!=required or row['sequence']!=index:raise ValueError('Survivalist CSV selection receipt changed')
  clause=policy['clauses'].get(row['clause_id'])
  if clause is None or row['cell_sha256']!=clause['cell_sha256']:raise ValueError('Survivalist CSV receipt source changed')
  values=row['terrains']
  if not isinstance(values,(tuple,list)) or not values or any(v not in TERRAINS for v in values) or len(set(values))!=len(values):raise ValueError('distinct actual Survivalist CSV terrains required')
  count=C.integer(row['feature_count'],'actual acquired Survivalist feature count',1)
  maximum=1+int(count>=2)+int(count>=4)+int(count>=6)
  if len(values)>maximum:raise ValueError('Survivalist CSV terrain count exceeds acquired features')
  minutes=C.integer(row['minutes'],'Survivalist CSV Extended Action minutes',1)
  started=C.integer(row['started_seconds'],'Survivalist CSV start time',0)
  finished=C.integer(row['completed_seconds'],'Survivalist CSV completion time',0)
  text(row['reason'],'GM Extended Action reason')
  if started<previous_end or finished-started!=minutes*60 or finished>e.elapsed_seconds:raise ValueError('Survivalist CSV action clock receipt changed')
  previous_end=finished
  frequency=row['frequency']
  if not isinstance(frequency,dict) or set(frequency)!={'kind','period','used'} or frequency['kind']!='daily' or frequency['used']!=1:raise ValueError('Survivalist CSV daily activation receipt changed')
  if frequency['period'] in periods:raise ValueError('Survivalist CSV daily period was consumed twice')
  periods.append(deepcopy(frequency['period']))
  if 'withdrawal' in row:
   withdrawal=row['withdrawal']
   if not isinstance(withdrawal,dict) or set(withdrawal)!={'seconds','reason'}:raise ValueError('Survivalist CSV withdrawal receipt changed')
   C.integer(withdrawal['seconds'],'Survivalist CSV withdrawal time',finished)
   if withdrawal['seconds']>e.elapsed_seconds:raise ValueError('Survivalist CSV withdrawal is from the future')
   text(withdrawal['reason'],'Survivalist CSV withdrawal reason')
 last=history[-1]
 if a.spec.get('frequency_state',{}).get('activations',{}).get(CSV_QUOTA)!=last['frequency']:raise ValueError('Survivalist CSV daily quota and action receipt disagree')
 active=state['active']
 if active is not None and (type(active) is not int or active!=len(history) or 'withdrawal' in last):raise ValueError('Survivalist CSV active selection changed')
 if active is None and 'withdrawal' not in last:raise ValueError('Survivalist CSV selection needs its actual withdrawal')
 sources=a.spec.get(GRANTS.KEY,{}).get('sources',{})
 live={token:row for token,row in sources.items() if row.get('kind')=='survivalist_csv_selection'}
 expected={} if active is None else {_csv_token(a,active):dict(kind='survivalist_csv_selection',grants={},owner_id=a.entity_id,rule_id=SURVIVALIST,clause_id=last['clause_id'],cell_sha256=last['cell_sha256'],selection_sequence=active,selection=deepcopy(last),lifetime='while class owned until replaced or withdrawn')}
 if live!=expected:raise ValueError('Survivalist CSV owned source and selection receipt disagree')


def csv_selected(e,a):
 _csv_validate(e,a)
 # Withdrawal of the actual class immediately removes both projections while
 # keeping the paid action and source history available for restoration.
 if not F.owned(a,SURVIVALIST):return ()
 base(e,a)
 state=a.spec[CSV_STATE]
 if state['active'] is None:return ()
 values=state['history'][-1]['terrains']
 count=feature_count(e,a);maximum=1+int(count>=2)+int(count>=4)+int(count>=6)
 if len(values)>maximum:raise ValueError('live acquired Survivalist features no longer support the selection')
 return tuple(values)


def _csv_talent_values(e,a,*,allow_rank_growth=False):
 F.require(e,a,TALENT);source(e,TERRAIN_SOURCE);available=selected(e,a)
 rank=a.spec.get('feat_ranks',{}).get(TALENT);C.integer(rank,'Terrain Talent acquired rank',1,2)
 record=a.spec.get('_survivalist_talents')
 if not isinstance(record,dict) or record.get('source')!=TALENT:raise ValueError('actual chosen Terrain Talents required')
 chosen_rank=C.integer(record.get('rank'),'Terrain Talent chosen rank',1,2)
 if chosen_rank!=rank and not (allow_rank_growth and chosen_rank<rank):raise ValueError('Terrain Talent chosen rank no longer acquired')
 values=record.get('terrains');state=a.spec[CSV_STATE];last=state['history'][-1]
 if (not isinstance(values,(tuple,list)) or any(not isinstance(v,str) or v not in TERRAINS for v in values)
     or len(values)!=chosen_rank*2 or len(set(values))!=len(values) or not set(values)<=set(last['terrains'])
     or state['active'] is not None and not set(values)<=set(available)):raise ValueError('Terrain Talent selection prerequisites no longer established')
 seconds=C.integer(record.get('selected_seconds'),'Terrain Talent selection time',last['completed_seconds'])
 if seconds>last.get('withdrawal',{}).get('seconds',e.elapsed_seconds):raise ValueError('Terrain Talent selection time is from the future')
 return tuple(values)


def select_csv_terrains(e,a,*,clause_id,terrains,minutes,reason,talent_terrains=None):
 import state_grants as GRANTS
 def apply(staged,actor):
  previous='_survivalist_talents' in actor.spec
  if previous:
   base(staged,actor)
   if CSV_STATE in actor.spec:_csv_talent_values(staged,actor,allow_rank_growth=True)
   else:talents(staged,actor)
   if talent_terrains is None:raise ValueError('CSV terrain reselection requires simultaneous Terrain Talent choices')
  row=_commit_csv_selection(staged,actor,clause_id,terrains,minutes,reason)
  if talent_terrains is not None:
   if previous:del actor.spec['_survivalist_talents']
   choose_talents(staged,actor,terrains=talent_terrains)
  return row
 return GRANTS.transition(e,a,apply,include_grid=e.grid is not None)


def _commit_csv_selection(e,a,clause_id,terrains,minutes,reason):
 import action_lifecycle as ACTION
 import frequency as FREQUENCY
 import state_grants as GRANTS
 base(e,a);policy=csv_policy(e.r);_csv_validate(e,a)
 if clause_id not in policy['clauses']:raise ValueError('explicit reviewed Survivalist CSV clause required')
 if a.spec.get('_survivalist_terrains'):raise ValueError('CSV daily choice cannot replace Markdown terrain mastery')
 if e.encounter_active:raise ValueError('Survivalist CSV selection requires noncombat Extended Action')
 if not isinstance(terrains,(tuple,list)) or not terrains:raise ValueError('explicit actual terrain choices required')
 values=tuple(terrain(value) for value in terrains)
 count=feature_count(e,a);maximum=1+int(count>=2)+int(count>=4)+int(count>=6)
 if len(set(values))!=len(values) or len(values)>maximum:raise ValueError('distinct terrains within acquired-feature capacity required')
 C.integer(minutes,'GM Extended Action minutes',1);text(reason,'GM Extended Action reason')
 if not ACTION.status_permission(e,a,'extended'):raise ValueError('Extended Action permission unavailable')
 if not FREQUENCY.activation_allowed(a,CSV_QUOTA,CSV_FREQUENCY,engine=e):raise ValueError('Survivalist CSV daily selection exhausted')
 FREQUENCY.consume_activation(a,CSV_QUOTA,CSV_FREQUENCY,engine=e)
 paid_frequency=deepcopy(FREQUENCY.state(a)['activations'][CSV_QUOTA])
 started=e.elapsed_seconds
 e.advance_time(minutes*60,[a]);ACTION.record_action(e,a,'extended')
 state=a.spec.setdefault(CSV_STATE,dict(owner_id=a.entity_id,acquisition_source=SURVIVALIST,history=[],active=None))
 if state['active'] is not None:GRANTS.revoke(a,_csv_token(a,state['active']),engine=e)
 sequence=len(state['history'])+1
 row=dict(sequence=sequence,clause_id=clause_id,cell_sha256=policy['clauses'][clause_id]['cell_sha256'],terrains=list(values),feature_count=count,started_seconds=started,completed_seconds=e.elapsed_seconds,minutes=minutes,reason=reason,frequency=paid_frequency)
 state['history'].append(row);state['active']=sequence
 GRANTS._source(a,_csv_token(a,sequence),'survivalist_csv_selection',owner_id=a.entity_id,rule_id=SURVIVALIST,clause_id=clause_id,cell_sha256=row['cell_sha256'],selection_sequence=sequence,selection=deepcopy(row),lifetime='while class owned until replaced or withdrawn')
 _csv_validate(e,a)
 return deepcopy(row)


def withdraw_csv_terrains(e,a,*,reason):
 import state_grants as GRANTS
 text(reason,'Survivalist CSV withdrawal reason')
 def apply(staged,actor):
  _csv_validate(staged,actor);state=actor.spec.get(CSV_STATE)
  if state is None or state['active'] is None:raise ValueError('actual active Survivalist CSV choice required')
  GRANTS.revoke(actor,_csv_token(actor,state['active']),engine=staged)
  state['history'][-1]['withdrawal']={'seconds':staged.elapsed_seconds,'reason':reason};state['active']=None
  _csv_validate(staged,actor)
 return GRANTS.transition(e,a,apply)


def validate_world(e,index):
 for actor in index.values():
  if CSV_STATE in actor.spec:_csv_validate(e,actor)
 __import__('survivalist_class').validate_world(e,index)

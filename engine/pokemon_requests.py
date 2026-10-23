"""Noncombat Pokemon requests and GM responses, ch06:157-161.
This adapter invokes native checks/capabilities. It does not invent obedience DCs,
classify prose, or merge noncombat requests with combat command authorization.
"""
from copy import deepcopy
from dataclasses import asdict,is_dataclass
import inspect,json
import common_checks as C

ACTIONS={'common_action','carry_check','drag_object','sprint','burrow_move','aerial_move','teleport','jump'}
EXCEPTIONS={'low_loyalty','severe_danger','moral_conflict'}

def _public(record):
 value=deepcopy(record)
 # Legacy saved requests may contain a secret GM observation.
 value.pop('loyalty_at_submission',None)
 return value


def _p():
 import pokemon_activities
 return pokemon_activities

def _options(value):
 if value is None:return {}
 if not isinstance(value,dict):raise ValueError('native action options must be a mapping')
 try:json.dumps(value,ensure_ascii=False,allow_nan=False)
 except (TypeError,ValueError) as exc:raise ValueError('request options must contain serializable facts, not callbacks or actors') from exc
 if any(k in value for k in ('actor','c','engine','self','trainer','pokemon')):raise ValueError('request cannot replace its actual Pokemon actor')
 return deepcopy(value)

def _target(e,actor,target):
 P=_p();P._outside(e);P._pokemon(target);P._owner(actor,target);P._text(target.spec.get('id'),'Pokemon identity')
 # Explicit GM world entries with duplicate identities must not select a different actor.
 for c in list(e.gm.everyone or [])+list(e.everyone or []):
  if c is not target and c.spec.get('id')==target.spec['id']:raise ValueError('ambiguous actual Pokemon identity')

def request(e,actor,*,target,request_id,intent,action='common_action',options=None,understanding=None):
 _target(e,actor,target);P=_p();P._text(request_id,'request identity');P._text(intent,'trainer request')
 if action not in ACTIONS:raise ValueError('request requires an existing noncombat check/capability action')
 import pokemon_understanding as UNDERSTANDING
 UNDERSTANDING.source(e)
 needs=UNDERSTANDING.requirements(understanding)
 opts=_options(options)
 if request_id in actor.spec.get('pokemon_requests',{}):raise ValueError('request identity already exists')
 record={'id':request_id,'trainer_id':actor.spec['id'],'pokemon_id':target.spec['id'],
  'intent':intent,'action':action,'requested_options':opts,'status':'awaiting_gm',
  'submitted_at':e.elapsed_seconds,'loyalty_context':'GM_private','responses':[],
  'understanding_requirements':needs,'understanding_assessment':None}
 actor.spec.setdefault('pokemon_requests',{})[request_id]=record
 return {'status':'awaiting_gm','request':_public(record),'result':C.PendingDecision('GM Pokemon response / optional check / ability use')}

def _check(record):return C.CheckResult(**record['check']) if record.get('check') is not None else None

def _facts(value):
 # Native movement records may contain nested CheckResults. Preserve only plain
 # facts in the trainer request history, while returning the native result as is.
 if is_dataclass(value):return _facts(asdict(value))
 if isinstance(value,dict):return {key:_facts(item) for key,item in value.items()}
 if isinstance(value,(list,tuple)):return [_facts(item) for item in value]
 return deepcopy(value)

def _finish(record,result,*,phase):
 record['last_phase']=phase
 if isinstance(result,C.PendingDecision):
  record['native_pending']=result.required
  if result.check is not None:
   record['check']=asdict(result.check)
   record['status']='awaiting_result' if phase in ('requested_check','ordinary') else 'native_pending'
  else:record['status']='native_pending'
 elif result is False:
  record['status']='not_executed';record['native_result']=False
 elif isinstance(result,C.ActionOutcome):
  record['status']='completed';record['outcome']=asdict(result)
 else:
  record['status']='completed';record['native_result']=_facts(result)
 return {'status':record['status'],'request':_public(record),'result':result}

def resolve(e,actor,*,target,request_id,decision,explanation,exceptions=None,options=None,
            skill=None,dc=None,roll_options=None,outcome=None,cost=None,failure_margin_accepted=False):
 _target(e,actor,target);P=_p();P._text(explanation,'GM Pokemon response explanation')
 record=actor.spec.get('pokemon_requests',{}).get(request_id)
 if not record or record['trainer_id']!=actor.spec['id'] or record['pokemon_id']!=target.spec['id']:raise ValueError('actual trainer/Pokemon request identity required')
 if record['status'] not in ('awaiting_gm','awaiting_result'):raise ValueError('request already consumed; native pending consequences use their own GM interface')
 if decision not in ('accept','refuse','check'):raise ValueError('GM must accept, refuse, or require a check')
 exceptions={} if exceptions is None else dict(exceptions)
 if set(exceptions)-EXCEPTIONS or any(type(v) is not bool for v in exceptions.values()):raise ValueError('GM exception context needs explicit low loyalty/danger/morality booleans')
 if record['status']=='awaiting_result' and (decision=='check' or options is not None or skill is not None or dc is not None or roll_options is not None):raise ValueError('already rolled request cannot change its action or obtain another roll')
 if decision!='check' and (skill is not None or dc is not None or roll_options is not None):raise ValueError('skill/DC/roll options require the GM check branch')
 C.validate_adjudication(outcome,explanation,cost,failure_margin_accepted)
 if record.get('understanding_requirements') is not None and options is not None and _options(options)!=record['requested_options']:raise ValueError('cannot replace execution options behind a scoped understanding assessment')
 if decision!='refuse':
  import pokemon_understanding as UNDERSTANDING
  UNDERSTANDING.require_request(e,actor,target,record)
 if decision=='check':
  if not isinstance(skill,str) or dc is None:raise ValueError('GM selected skill and DC required')
  C.integer(dc,'DC');prepared=P._preflight(e,target,skill,_options(roll_options))
 opts=_options(options) if options is not None else deepcopy(record.get('execution_options',record['requested_options']))
 if decision=='refuse':
  record['responses'].append(dict(decision=decision,explanation=explanation,exceptions=exceptions,at=e.elapsed_seconds))
  record.update(status='refused',refusal_reason=explanation)
  return {'status':'refused','request':_public(record),'result':None}
 if record['status']=='awaiting_result':
  result=C.adjudicate(_check(record),outcome=outcome or 'success',description=explanation,cost=cost,failure_margin_accepted=failure_margin_accepted)
  if isinstance(result,C.PendingDecision):return {'status':'awaiting_result','request':_public(record),'result':result}
  if record['action']=='common_action' or result.outcome=='failure':
   record['responses'].append(dict(decision=decision,explanation=explanation,exceptions=exceptions,at=e.elapsed_seconds))
   if record['action']!='common_action':record['precondition_outcome']=asdict(result)
   return _finish(record,result,phase='ordinary' if record['action']=='common_action' else 'failed_precondition')
  record['precondition_outcome']=asdict(result)
 # Bind native argument shape before any mark/roll/cost; no arbitrary callback execution.
 if decision!='check':
  if record['action']=='common_action':
   opts.setdefault('mode','no_roll');opts.setdefault('outcome',outcome or 'success');opts.setdefault('description',explanation)
   opts.setdefault('declaration',{'action':record['intent'],'intent':record['intent'],'context':'GM-controlled noncombat Pokemon'})
  inspect.signature(getattr(e,record['action'])).bind(target,**opts)
 record['execution_options']=deepcopy(opts)
 record['responses'].append(dict(decision=decision,explanation=explanation,exceptions=exceptions,at=e.elapsed_seconds))
 record['status']='executing'
 try:
  if decision=='check':
   result=e.common_action(target,skill,dc,mode='skill',declaration={'action':record['intent'],'context':'GM requested Pokemon check'},**prepared)
   return _finish(record,result,phase='requested_check')
  result=getattr(e,record['action'])(target,**opts)
  return _finish(record,result,phase='ordinary' if record['action']=='common_action' else 'native')
 except Exception as exc:
  # Never turn a post-roll/producer exception into a fresh execution right.
  record.update(status='execution_error',error_type=type(exc).__name__,error_message=str(exc))
  raise

ACTIVITIES={'request_help':request,'resolve_help':resolve}

"""Explicit legacy Engine binding for the admitted common-check protocol.

The installed Registry controls authority. This binding captures native actors,
records check/adjudication receipts, and rejects changed host context or restore.
It does not turn narrative descriptions into game effects or advance task time.
"""
import importlib
import hashlib,json
import held_equipment as HELD
from pathlib import Path


import resolution_transaction as _FINGERPRINTS

def _plain(value):
    if value is None or type(value) in (str,int,bool):return value
    if type(value) is float:return {'host_float_hex':value.hex()}
    if isinstance(value,dict):return {str(k):_plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_plain(v) for v in value]
    if isinstance(value,(set,frozenset)):return sorted((_plain(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
    raise ValueError('unsupported host context value: '+type(value).__name__)


def _digest(value):return _FINGERPRINTS.json_fingerprint(_plain(value), sort_keys=True, compact=True, allow_nan=True)


def host_context(engine,actors):
    if not isinstance(actors,dict) or not actors or any(type(k) is not str or not k for k in actors):raise ValueError('explicit actor identity mapping required')
    if len({id(c) for c in actors.values()})!=len(actors):raise ValueError('one actor cannot have duplicate identities')
    ranks=engine.r.mech('gameplay/skill-rank-dice')['by_rank_name']
    ordinary=engine.r.mech('gameplay/skill-check')
    actor_rows={}
    for key,c in actors.items():
        if getattr(c,'r',None) is not engine.r:raise ValueError('actor must belong to this native rule context')
        actor_rows[key]={name:getattr(c,name,None) for name in ('spec','hp','dead','fainted','conditions','custom_conditions','buffs','modifiers','abilities','abilities_suppressed','level','injuries','registry','coats','blessings')}
        actor_rows[key]['held_equipment']=HELD.entries(c)
    profile=vars(engine.r.ruleset)
    # Record concrete selected rule data as well as profile policy. This checks
    # staleness, not a proof that all source modifiers/exceptions were collected.
    return _plain(dict(actors=actor_rows,profile=profile,rank_rule=ranks,ordinary_rule=ordinary,
        time={name:getattr(engine,name,None) for name in ('elapsed_seconds','round_no','encounter_active','session_id','session_epoch','weather','field')},
        rulings={name:getattr(engine.rulings,name,None) for name in ('formulas','mech','effects','situational','answers')},
        hooks={key:tuple(id(fn) for fn in values) for key,values in engine.rulings.hooks.items()},provider=id(engine.rulings.provider)))


def actor_projection(engine,actors,configuration):
    ranks=engine.r.mech('gameplay/skill-rank-dice')['by_rank_name'];out={}
    for key,c in actors.items():
        skills={}
        for skill,rank in c.spec.get('skills',{}).items():
            if type(rank) is not str or rank not in ranks:raise ValueError('unresolved native skill rank')
            expression=ranks[rank].get('dice')
            if expression not in tuple(str(i)+'d6' for i in range(1,7)):raise ValueError('specialized dice require source refinement')
            skills[skill]=int(expression[0])
        if type(c.hp) is not int or type(getattr(c,'dead',False)) is not bool or type(getattr(c,'fainted',False)) is not bool:raise ValueError('typed native life state required')
        out[key]={'skills':skills,'ordinary_default':key in configuration.get('ordinary_default_actor_ids',()),'hp':c.hp,'dead':getattr(c,'dead',False),'fainted':getattr(c,'fainted',False),'conditions':list(c.conditions),'injuries':c.injuries,'modifier_sources':[name for name in ('abilities','buffs','modifiers','registry','coats','blessings','custom_conditions') if getattr(c,name,None)]+(['item'] if HELD.any_held(c) else [])+['spec:'+name for name in ('feats','edges','features') if c.spec.get(name)]}
    return out


class EngineCheckBinding:
    def __init__(self,engine,registry,registration,actors,configuration,principals):
        # The registration's module determines the single root-module namespace;
        # legacy engine.py can also be imported as the top-level name 'engine'.
        old=getattr(engine,'_root_common_binding',None)
        if old is not None and old._epoch==getattr(engine,'_root_common_epoch',0):raise ValueError('one shared root common-check binding per Engine epoch; explicit rebase required')
        module=importlib.import_module(type(registry).__module__)
        if type(registry) is not getattr(module,'Registry',None):raise TypeError('root Registry required')
        if Path(module.__file__).resolve()!=Path(__file__).with_name('root_admission.py').resolve():raise ValueError('Registry belongs to another implementation checkout')
        prefix=module.__package__
        self.api=importlib.import_module(prefix+'.root_common_checks')
        self.rm=importlib.import_module(prefix+'.root_machine')
        self.ra=module
        checked=registry.checked(registration)
        if isinstance(checked,module.Finding):raise ValueError(checked.detail)
        cert,_=checked
        if configuration.get('combat_active') is not engine.encounter_active:raise ValueError('configured combat context differs from native Engine')
        if configuration.get('mode')!=cert.mode or configuration.get('catalog_hash')!=cert.catalog_hash:raise ValueError('configuration differs from admitted policy scope')
        self.engine=engine;self.actors=dict(actors);self._actor_refs=tuple((k,id(v)) for k,v in self.actors.items())
        self._epoch=getattr(engine,'_root_common_epoch',0)
        self._context=host_context(engine,self.actors);self._hash=_digest(self._context)
        native_profile=_digest({k:self._context[k] for k in ('profile','rank_rule','ordinary_rule')})
        if cert.mode=='source':
            if any(getattr(engine.rulings,name,None) for name in ('formulas','mech','effects','situational','answers')) or any(engine.rulings.hooks.values()) or engine.rulings.provider is not None:
                raise ValueError('source common-check binding requires refined external rulings/modifier composition')
            artifact=configuration.get('native_binding_artifact')
            if type(artifact) is not str or artifact not in cert.chain['adapter_refinement'] or artifact not in cert.artifacts:
                raise ValueError('source Engine binding needs a separately reviewed pinned native-profile relation')
            evidence=json.loads((registry.root/artifact).read_text(encoding='utf-8'))
            expected={'kind':'common-check-native-profile-v1','profile_hash':cert.profile_hash,'catalog_hash':cert.catalog_hash,'native_profile_hash':native_profile}
            if evidence!=expected:raise ValueError('native profile does not match admitted source binding evidence')
        self.configuration=configuration
        snapshot=self.api.initial_snapshot(cert.profile_hash,actor_projection(engine,self.actors,configuration),configuration)
        self.runtime=module.Runtime(registry,self.rm.Machine(snapshot),principals)
        self.session=self.api.CheckSession(self.runtime,registration)
        self._recorded=set()
        self.engine._root_common_binding=self

    def _fresh(self):
        if getattr(self.engine,'_root_common_epoch',0)!=self._epoch:return self.ra.Finding('RejectedStaleOrMismatch','Engine restore invalidated this binding')
        if tuple((k,id(v)) for k,v in self.actors.items())!=self._actor_refs:return self.ra.Finding('RejectedStaleOrMismatch','native actor identities changed')
        try:current=_digest(host_context(self.engine,self.actors))
        except Exception as exc:return self.ra.Finding('RejectedStaleOrMismatch','native context unavailable: '+str(exc))
        if current!=self._hash:return self.ra.Finding('RejectedStaleOrMismatch','native actor/rule/time context changed')
        return None

    def begin(self,event_id,request_key):
        issue=self._fresh()
        if issue:return issue
        return self.session.begin(event_id,request_key)

    def submit(self,ticket):
        issue=self._fresh()
        if issue:return issue
        result=self.runtime.submit(ticket)
        self._record(result)
        return result

    def result(self,event_id):
        issue=self._fresh()
        if issue:return issue
        return self.session.result(event_id)

    def pending(self,ticket):
        issue=self._fresh()
        if issue:return issue
        return self.runtime.get_input(ticket)

    def answer(self,pending,principal,value):
        issue=self._fresh()
        if issue:return issue
        result=self.runtime.answer(pending,principal,value)
        self._record(result)
        return result

    def _record(self,result):
        if not isinstance(result,self.rm.Outcome) or result.tag!='Completed' or result.event_id in self._recorded:return
        record=dict(event_id=result.event_id,host_epoch=self._epoch,host_context_hash=self._hash,results=self.rm.thaw(result.results),
            scope='common check and explicit adjudication receipt; no automatic world effects/time advance',source_gameplay_certified=False)
        if not hasattr(self.engine,'_root_common_receipts'):self.engine._root_common_receipts=[]
        self.engine._root_common_receipts.append(record);self._recorded.add(result.event_id)


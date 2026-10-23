"""Synthetic registration harness; source facts must be independently admitted."""
from pathlib import Path
import sys,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from engine import root_common_checks as c,root_machine as m,root_admission as a,root_inputs as i
PROFILE='a'*64;CATALOG='b'*64

def actor(rank=2,**kw):
    return dict(skills={'athletics':rank},ordinary_default=True,hp=50,dead=False,fainted=False,conditions=[],injuries=0,modifier_sources=[],**kw)

def setup(decision=None,actors=None,requests=None):
    actors=actors or {'a':actor(),'b':actor(3),'helper':actor(3)}
    decision=decision or {'mode':'dc','skill':'athletics','dc':7}
    req={'intent':'Attempt the declared ordinary task.','actors':['a'],'decisions':[decision],'outcomes':[{'outcome':'success','description':'Succeeded.'},{'outcome':'failure','description':'Failed.'},{'outcome':'success_with_cost','description':'Passed with cost.','cost':'Explicit consequence to adjudicate','failure_margin_accepted':True},{'outcome':'other','description':'Recorded.'}],'context_obligations':[],'modifier_policy':'none'}
    config={'mode':'synthetic','catalog_hash':CATALOG,'source_refs':['synthetic:ordinary-common-checks'],'gm_ids':['gm'],'roller_ids':{x:[x] for x in actors},'skill_catalog':['athletics','survival'],'combat_active':False,'requests':requests or {'check':req}}
    state=c.initial_snapshot(PROFILE,actors,config)
    files=['engine/'+name+'.py' for name in ('root_machine','root_resolution','root_admission','root_inputs','root_scheduler','root_children','common_checks','root_common_checks')]+['tools/common_check_fixture.py','tools/common_check_synthetic_evidence.txt']
    artifacts={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
    chain={k:('tools/common_check_synthetic_evidence.txt',) for k in a.CHAIN};chain['adapter_refinement']=('engine/root_common_checks.py',)
    cert=a.Certificate('common-checks-synthetic','synthetic',PROFILE,CATALOG,'common.checks',c.EVENT_KIND,c.ASPECTS,tuple(config['source_refs']),('synthetic registration executes actual ordinary arithmetic',),'ordinary common checks with explicit external domain',c.ADAPTER_ID,artifacts,chain,('positive',),('negative',))
    registry=a.Registry(ROOT,a.TrustedPolicy('test-only','synthetic',{cert.id:cert.fingerprint()}),(c.adapter(),))
    handle=registry.verify_registration(cert)
    assert type(handle) is a.Registration,handle
    principals={x:i.Principal(x) for x in ['gm']+list(actors)}
    runtime=a.Runtime(registry,m.Machine(state),principals=tuple(principals.values()))
    return c.CheckSession(runtime,handle),principals,config

def start(session,key='check',event='e'):
    t=session.begin(event,key);assert type(t) is a.Ticket,t
    out=session.submit(t);assert out.tag=='AwaitingInput',out
    return t

def answer(session,ticket,principal,value):
    pending=session.pending(ticket);assert type(pending) is a.PendingInput,pending
    return session.answer(pending,principal,value)

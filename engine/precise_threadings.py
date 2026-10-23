"""Precise Threadings values on the shared capability-parameter acquisition owner."""
import state_grants as G,skill_modifiers as S,capability_parameter_edges as P
SOURCE='poke_edge/꼼꼼한-실'
CAPABILITY='capability/실-날리기'
ALIASES={SOURCE:SOURCE,'꼼꼼한 실':SOURCE,'Precise Threadings':SOURCE}


def owned(actor):
    return bool({S.key(x) for x in ('실 날리기','실날리기','Threaded',CAPABILITY)} &
                {S.key(x) for x in G.effective_capabilities(actor)})


def records(actor):return P.records(actor,SOURCE)
def definition(rules):return P.definition(rules,SOURCE)
def validate(actor,*,allow_lost=False):return P.validate(actor,SOURCE,allow_lost=allow_lost)
def parameters(actor):return P.parameters(actor,SOURCE)
def reconcile(actor,*,reason):return P.reconcile(actor,reason=reason,source=SOURCE)
def teach(engine,owner,target,spec,**options):return P.teach(engine,owner,target,spec,**options)

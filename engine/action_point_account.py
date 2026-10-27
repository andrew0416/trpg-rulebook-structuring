"""Live AP account over the canonical actor sheet, with no copied balance.

The actor reference is retained, not its spec dict: native transactions may
replace that dict. Account handles are derived and never enter saved graphs.
"""
import arithmetic_policy as M
from types import MappingProxyType

SOURCE = "gameplay/action-points"


class ActionPointAccount:
    """Own AP validation, availability, spending, binding and recovery."""

    __slots__ = ("actor",)

    def __init__(self, actor):
        self.actor = actor

    def has_accounting(self):
        c = self.actor
        import temporary_ap as TEMP
        return bool(TEMP.live(c)) or any(c.spec.get(k,0) for k in ('ap_spent','ap_removed','ap_bound'))

    def validate(self, *, source_required=True):
        """Read-only whole ledger. AP-free actors do not need an AP source policy."""
        c = self.actor
        if type(c.level) is not int or c.level<0:
            raise ValueError("actual nonnegative whole level required for AP")
        for key in ("ap_spent","ap_removed"):
            if type(c.spec.get(key,0)) is not int or c.spec.get(key,0)<0:
                raise ValueError("AP usage must be nonnegative whole points")
        bound=c.spec.get("ap_bound",0)
        if isinstance(bound,dict):
            if any(type(k) is not str or not k.strip() for k in bound):raise ValueError("bound AP needs actual effect identities")
            amounts=list(bound.values())
        else:amounts=[bound]
        if any(type(v) is not int or v<0 for v in amounts):raise ValueError("bound AP must be nonnegative whole points")
        if 'nicolette_gym_ap' in c.spec:
            import nicolette_gym as NICOLETTE
            NICOLETTE.ap_policy(c)
        import temporary_ap as TEMP
        TEMP.available(c)
        if not source_required:return
        if c.r._selected_rule(SOURCE) != SOURCE:
            raise ValueError("selected AP source requires its own resource policy")
        M.validate_source(c.r)
        rulings=getattr(c.r,"rulings",None)
        if rulings is not None and (getattr(rulings,"mech",{}).get(SOURCE) or getattr(rulings,"effects",{}).get(SOURCE)):
            raise ValueError("overridden AP source requires its own resource policy")

    def extended_rest(self, *, request_id=None):
        c = self.actor
        self.validate(source_required=bool(c.spec.get('ap_removed',0)))
        import recovery_receipts as RECOVERY
        receipt=RECOVERY.execute(c,resource='ap_removed',source=SOURCE,request_id=request_id,
            policy='qualified_extended_rest',read=lambda:c.spec.get('ap_removed',0),
            qualify=lambda:{'eligible':True,'reason':'native qualified extended rest'},
            commit=lambda:c.spec.__setitem__('ap_removed',0))
        if request_id is not None:return receipt

    def maximum(self):
        c = self.actor
        self.validate(source_required=c.kind=='trainer' or self.has_accounting())
        if c.kind != "trainer":return 0
        sample=c.spec.get('nicolette_gym_ap')
        level=max(c.level,sample['ap_level']) if sample is not None else c.level
        import chef_cooking as CHEF
        return 5 + M.ratio(level,5) + (sample['bonus_ap'] if sample is not None else 0) + CHEF.max_ap_bonus(c)

    def available(self):
        c = self.actor
        import combat_timing as TIMING
        if any(record.get("ap_forbidden") for record in TIMING.records(c)):return 0
        # ap_removed already existed in downtime saves; do not recover it at scene end.
        bound=c.spec.get("ap_bound",0)
        if isinstance(bound,dict):bound=sum(bound.values())
        import temporary_ap as TEMP
        return max(0,self.maximum()-c.spec.get("ap_spent",0)-c.spec.get("ap_removed",0)-bound+TEMP.bound_amount(c))+TEMP.available(c)

    def charge(self, amount, *, mode='spend', instance_id=None, temporary_binding_owner=None, retain_receipt=False):
        """Native ledger operation, called inside the admitted effect transaction.

        Bind callers own activation/end semantics; this function grants no effect or
        permission. An instance identity is a reservation, never a second AP pool.
        """
        c = self.actor
        self.validate()
        if type(retain_receipt)is not bool or retain_receipt and mode!='spend':raise ValueError('only actual AP spending may retain a refund receipt')
        if type(amount) is not int or amount<0:raise ValueError('AP charge requires nonnegative whole points')
        if mode not in ('spend','drain','bind'):raise ValueError('unsupported AP charge mode')
        if mode=='bind':
            if type(instance_id) is not str or not instance_id.strip() or amount==0:
                raise ValueError('AP binding requires a positive amount and effect identity')
            bound=c.spec.get('ap_bound',{})
            if bound==0:bound={}
            if type(bound) is not dict:raise ValueError('legacy bound AP requires identity reconciliation')
            if instance_id in bound:raise ValueError('AP effect identity already reserved')
        elif instance_id is not None:raise ValueError('only bound AP has an effect reservation')
        if amount>self.available():raise ValueError('insufficient available AP')
        import temporary_ap as TEMP
        temporary_before={row['id']:len(row['payments']) for row in TEMP.live(c)}
        ordinary = TEMP.charge(c,amount,ordinary_available=self.available()-TEMP.available(c),mode=mode,instance_id=instance_id,binding_owner=temporary_binding_owner)
        if mode=='bind':c.spec['ap_bound']={**bound,instance_id:amount}
        elif ordinary:
            key='ap_removed' if mode=='drain' else 'ap_spent'
            c.spec[key]=c.spec.get(key,0)+ordinary
        if not retain_receipt:return
        return {'actor_id':c.entity_id,'mode':mode,'amount':amount,'ordinary':ordinary,
                'temporary':[{'grant_id':row['id'],'index':index,'amount':payment['amount']}
                    for row in TEMP.live(c) for index,payment in enumerate(row['payments'])
                    if index>=temporary_before[row['id']]],'refunded':False}

    def refund_spend(self, receipt):
        """Refund a native producer's one retained spend receipt, never Drain/Bind.

        The source owner authenticates its trigger and retains this same mutable
        receipt in its completion. This layer validates and settles the funding.
        """
        c=self.actor;self.validate()
        if (type(receipt)is not dict or set(receipt)!={'actor_id','mode','amount','ordinary','temporary','refunded'}
                or receipt['actor_id']!=c.entity_id or receipt['mode']!='spend' or receipt['refunded'] is not False
                or type(receipt['ordinary'])is not int or receipt['ordinary']<0
                or type(receipt['amount'])is not int or receipt['amount']<0
                or receipt['ordinary']>c.spec.get('ap_spent',0)):
            raise ValueError('one actual unrefunded AP spend receipt required')
        import temporary_ap as TEMP
        TEMP.refund_spend(c,receipt['temporary'],expected=receipt['amount']-receipt['ordinary'])
        if receipt['ordinary']:c.spec['ap_spent']-=receipt['ordinary']
        receipt['refunded']=True
        return receipt['amount']

    def release_binding(self, instance_id, *, expected_amount):
        """Settle a reservation after its native owner has validated effect ending."""
        c = self.actor
        self.validate()
        bound=c.spec.get('ap_bound')
        if (type(instance_id) is not str or not instance_id.strip()
                or type(expected_amount) is not int or expected_amount<=0
                or type(bound) is not dict or bound.get(instance_id)!=expected_amount):
            raise ValueError('AP release requires the exact live reservation')
        import temporary_ap as TEMP
        TEMP.release(c,instance_id)
        del bound[instance_id]
        return expected_amount

    def end_scene(self, *, request_id=None):
        c = self.actor
        self.validate(source_required=self.has_accounting())
        import recovery_receipts as RECOVERY
        receipt=RECOVERY.execute(c,resource='ap_spent',source=SOURCE,request_id=request_id,
            policy='scene_end',read=lambda:c.spec.get('ap_spent',0),
            qualify=lambda:{'eligible':True,'reason':'native scene end'},
            commit=lambda:c.spec.__setitem__('ap_spent',0) if 'ap_spent' in c.spec else None)
        if request_id is not None:return receipt

    def identified_bindings(self, *, allow_missing=False):
        """Read exact live reservations; callers cannot edit the returned view."""
        self.validate()
        bound = self.actor.spec.get("ap_bound", {} if allow_missing else None)
        if type(bound) is not dict or any(
            type(key) is not str or not key.strip() or type(value) is not int or value <= 0
            for key, value in bound.items()
        ):
            raise ValueError("identified positive AP reservations required")
        used = sum(bound.values()) + self.actor.spec.get("ap_spent", 0) + self.actor.spec.get("ap_removed", 0)
        import temporary_ap as TEMP
        if used - TEMP.bound_amount(self.actor) > self.maximum():
            raise ValueError("AP accounting exceeds maximum")
        return MappingProxyType(bound)

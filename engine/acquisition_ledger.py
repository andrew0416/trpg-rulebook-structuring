"""Native acquisition evidence over the existing source-grant ledger.

This object does not approve acquisitions or infer unrecorded historical costs.
Handles follow actor.spec and do not add another ledger or saved graph node.
"""
from copy import deepcopy


class AcquisitionLedger:
    __slots__ = ("actor",)

    def __init__(self, actor):
        self.actor = actor

    def read(self, engine):
        actor = self.actor
        import world_entities as W,grant_payments as PAY
        W.require_actors(engine,actor,actor)
        PAY.validate(actor)
        state=actor.spec.get('state_grants',{});result=[]
        for identity,payment in state.get('payments',{}).items():
            request=payment.get('request',{})
            refunded={child for row in payment['refunds'] for child in row['sources']}
            forfeited={child for row in payment['refunds'] if row.get('refund_mode')=='none' for child in row['sources']}
            declarations={row['source_id']:row for row in request.get('grants',[])}
            executions=[row for row in getattr(engine,'_source_policy_executions',{}).values()
                if row.get('target_id')==actor.entity_id and row.get('grants_executed') is True
                and row.get('grant_operation')=='acquire' and row.get('grant_result',{}).get('group_id')==identity]
            providers={row['actor_id'] for row in executions}
            children=[]
            for child in payment['children']:
                live=state.get('sources',{}).get(child)
                children.append({'child_id':child,'parent_id':identity,
                    'state':'withdrawn_without_refund' if child in forfeited else 'refunded' if child in refunded else 'active' if live is not None else 'ended',
                    'grants':deepcopy(payment['grant_snapshot'][child]),
                    'declaration':deepcopy(declarations.get(child)),
                    'payment_ref':identity,'individual_debit':None,
                    'refund_allocation':None if payment['allocation'] is None else payment['allocation'][child]})
            result.append({'schema':1,'receipt_id':identity,'basis':'native_group_payment',
                'source_id':payment['acquisition']['rule_id'],'recipient_id':actor.entity_id,
                'provider_id':next(iter(providers)) if len(providers)==1 else None,
                'source_owner_id':request.get('owner_id'),'execution_ids':[row['execution_id'] for row in executions],
                'lifetime':request.get('lifetime'),
                'provenance_complete':payment['version']==2,
                'debit':{'payer_id':actor.entity_id,'resource':'tutor_points','amount':payment['paid']},
                'refunded':sum(row['amount'] for row in payment['refunds']),
                'refunds':deepcopy(payment['refunds']),'children':children})
        paid_children={child for payment in state.get('payments',{}).values() for child in payment['children']}
        sources=[('source/'+key,key,row,'active') for key,row in state.get('sources',{}).items()
                 if key not in paid_children and row.get('grants')]
        sources.extend(('ended-source/'+str(index),entry['source_id'],entry['record'],'ended')
                       for index,entry in enumerate(state.get('ended_sources',[])))
        for identity,key,row,status in sources:
            result.append({'schema':1,'receipt_id':identity,'basis':'native_source_grant',
                'source_id':row.get('rule_id'),'grant_source_id':key,'recipient_id':actor.entity_id,
                'provider_id':None,'source_owner_id':row.get('owner_id'),'lifetime':row.get('lifetime'),
                'state':status,'grants':deepcopy(row['grants']),
                'debit':None,'declared_refundable_points':row.get('tutor_points'),
                'metadata':{k:deepcopy(row[k]) for k in ('kind','rank','branch','specialization','parent_id') if k in row}})
        # These records are producer-written acquisitions. Missing old provider or
        # time values stay unknown; current ownership cannot repair old evidence.
        for index,row in enumerate(actor.spec.get('learned_poke_edges',[])):
            cost=row.get('point_cost')
            if type(cost) is not int or cost<0:continue
            result.append({'schema':1,'receipt_id':'poke-edge/'+str(index),
                'basis':'native_learned_edge','source_id':row['source'],
                'recipient_id':actor.entity_id,'provider_id':row.get('trainer_id'),
                'lifetime':row.get('lifetime'),'state':row.get('status'),
                'debit':{'payer_id':actor.entity_id,'resource':'tutor_points','amount':cost},
                'selection':{k:deepcopy(row[k]) for k in ('skill','stat','capability','move_id','rank_before') if k in row},
                'completed_at':row.get('completed_at'),'native_record':deepcopy(row)})
        import crafting_products as PRODUCTS
        result.extend(PRODUCTS.receipts(engine,actor))
        import trainer_feature_acquisition as TRAINER_FEATURES
        result.extend(TRAINER_FEATURES.receipts(actor))
        return result

    def account(self, engine):
        """Recorded inflows, balance observations and acquisitions, without inferred spending."""
        actor = self.actor
        import world_entities as W,pokemon_progression as P
        W.require_actors(engine,actor,actor)
        if actor.kind!='pokemon':raise ValueError('Tutor Point account requires actual Pokemon')
        P.validate(actor.spec)
        level=actor.spec.get(P.LEVEL_STATE,{})
        entries=[]
        if level:
            origin=level['origin']
            entries.append({'kind':'initial_award' if origin=='fresh_creation' else 'initial_observation',
                'origin':origin,'source_id':level['source'],'level':level['initial_level'],
                'amount':level.get('initial_balance'),'historical_amount_known':level.get('initial_balance') is not None})
        entries.extend({'kind':'level_award','source_id':row['source'],'level':row['level'],
            'amount':row['points'],'destination_at_award':row['destination']} for row in level.get('awards',[]))
        entries.extend({'kind':'balance_observation',**deepcopy(row)}
                       for row in actor.spec.get('tutor_point_observations',[]))
        return {'schema':1,'entity_id':actor.entity_id,'resource':'tutor_points',
                'balance_known':'tutor_points' in actor.spec,'balance':actor.spec.get('tutor_points'),
                'pending_awards':level.get('pending_points'),
                'resource_events':entries,'acquisitions':self.read(engine),
                'complete_spending_history':False}

    def record_payment(self, identity, record):
        import state_grants as G
        payments = G.state(self.actor).setdefault("payments", {})
        if identity in payments:
            raise ValueError("acquisition payment identity already recorded")
        payments[identity] = deepcopy(record)

    def commit_refunds(self, plans, reason):
        for plan in plans:
            row = self.actor.spec["state_grants"]["payments"][plan["group_id"]]
            row["allocation"] = deepcopy(plan["allocation"])
            row["refunds"].append({
                "sources": list(plan["sources"]), "amount": plan["amount"], "reason": reason
            })
            if plan.get("refund_mode") == "none":
                row["refunds"][-1]["refund_mode"] = "none"

    def record_refund(self, identity, record):
        import state_grants as G
        refunds = G.state(self.actor).setdefault("payment_refunds", {})
        if identity in refunds:
            raise ValueError("acquisition refund identity already recorded")
        refunds[identity] = deepcopy(record)

    def end_source(self, source_id):
        """Archive actual native grants, then end their current ownership."""
        state = self.actor.spec.get("state_grants", {})
        row = state.get("sources", {}).get(source_id)
        if row is not None and (row.get("grants") or row.get("retraining")) and not row.get("payment_id"):
            state.setdefault("ended_sources", []).append({
                "source_id": source_id, "record": deepcopy(row)
            })
        state.get("sources", {}).pop(source_id, None)

"""Source adapters implement one item-use interface; families describe lifecycles.

Stock storage (quantity or physical instance) stays in item_stock. A family's
name never grants an item permission, timing, effects or an automatic refund.
Use methods retain their native result and source receipts for existing callers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeVar
import common_checks as C


class UseFamily(str, Enum):
    IMMEDIATE = 'immediate'
    STORED_EFFECT = 'stored_effect'
    DEPLOYED = 'deployed'
    LOADED = 'loaded'
    TRANSFORM = 'transform'


FAMILY_CONTRACTS = {
    UseFamily.IMMEDIATE: 'spend the item at admitted application; apply the sourced result',
    UseFamily.STORED_EFFECT: 'spend the item; retain a separately identified effect for later activation',
    UseFamily.DEPLOYED: 'leave possession; retain the thrown, placed or attached object/state',
    UseFamily.LOADED: 'move contents into a reusable body; discharge contents under its own trigger',
    UseFamily.TRANSFORM: 'consume admitted inputs and create the sourced output/state together',
}


@dataclass(frozen=True)
class UseRequest:
    user: Any
    target: Any
    item_name: str
    source_id: str | None
    free: bool = False
    accepted: bool = True
    duration_minutes: int | None = None
    duration_reason: str | None = None
    count: int = 1
    food_policy: str | dict | None = None
    medicine_source_choice: Any = None
    selected_move: str | None = None
    held_selection: Any = None
    container_selection: Any = None
    shell_batch_id: str | None = None
    fixed_accuracy: int | None = None
    resumable: bool = False
    request_id: str | None = None
    aim: Any = None
    source_selection: Any = None
    selected_stat: str | None = None
    owner_consent_by: Any = None


RequestT = TypeVar("RequestT", contravariant=True)


class UseAdapter(Protocol[RequestT]):
    family: UseFamily | None

    def execute(self, engine, request: RequestT): ...


class ItemUse(ABC):
    """Template shared by item-use adapters; source-specific preparation is pure.

    Commit implementations own their observation/transaction boundary. A known
    die result must not be erased by a generic rollback around every use.
    """
    family: UseFamily | None
    physical = False
    silent_refusal = False
    requires_acceptance = True

    def execute(self, engine, request):
        import turn as TURN, item_stock as STOCK
        r=request
        if r.medicine_source_choice is not None and r.source_id not in __import__('restorative_items').HELD_CONSUMABLES:
            raise ValueError('medicine source choice requires a restorative or X item')
        if type(r.accepted) is not bool or type(r.free) is not bool:
            raise ValueError('item consent and cost-waiver declarations must be boolean')
        C.integer(r.count,'actual whole item count',1)
        if (r.selected_stat is not None or r.owner_consent_by is not None) and not isinstance(self,VitaminUse):raise ValueError('stat choice and owner consent require a Stat Suppressant')
        if r.aim is not None and not isinstance(self,(CaltropsUse,SmokeBallUse,RepelUse)):raise ValueError('item placement requires a reviewed deployed tool')
        if r.fixed_accuracy is not None and not isinstance(self,(AttackUse,RepelUse)):raise ValueError('fixed accuracy requires a reviewed consumable attack')
        if type(r.resumable) is not bool:raise ValueError('explicit item clock mode required')
        if r.request_id is not None and not r.resumable:raise ValueError('item request identity requires resumable time')
        if r.resumable:
            if not isinstance(self,(ExtendedIntake,BandageUse)):raise ValueError('this item has no resumable intake/application')
            if not isinstance(r.request_id,str) or not r.request_id.strip():raise ValueError('identified timed item use required')
            if isinstance(self,BandageUse) and (r.container_selection is not None or r.shell_batch_id is not None):
                raise ValueError('bandages require their actual quantity or held stock')
            # An admitted shell/physical intake may already have paid its stock.
            # Its native consumer checks the original request before any replay.
            if r.request_id in getattr(engine,'_clock_invocations',{}):
                pending=self.prepare(engine,r)
                return pending if pending is not None else self.commit(engine,r)
        if r.container_selection is not None or r.shell_batch_id is not None:
            STOCK.prepare(engine,r.user,r.source_id,held_selection=r.held_selection,container_selection=r.container_selection,shell_batch_id=r.shell_batch_id,count=r.count)
            if not isinstance(self,(ExtendedIntake,AttackUse)):return C.PendingDecision('Selected contents need their source-specific effect consumer')
        if r.held_selection is not None:
            stock=STOCK.prepare(engine,r.user,r.source_id,held_selection=r.held_selection,count=r.count,equipment_slots=self.stock_slots(r),source_selection=r.source_selection)
            if isinstance(r.held_selection,str) and getattr(engine,'_physical_objects',{}).get(r.held_selection,{}).get('telekinetic_holder_id')==r.user.entity_id:
                __import__('telekinetic').item_target(engine,r.user,r.held_selection,r.target)
            if not self.supports_physical(r):
                return C.PendingDecision('Actual held-instance consumption needs its sourced completion adapter; no inventory, action or instance consumed',basis={'holder_id':r.user.entity_id,'held_stock':stock,'source':r.source_id,'status':'unimplemented_held_consumption'})
        if not TURN.can_act(engine,r.user):return (0,0)
        if not r.accepted and self.requires_acceptance:
            if self.silent_refusal and r.held_selection is not None:return {'status':'refused'}
            engine.log(f'  {r.target.name}: {r.item_name} 사용 거부 → 미사용','ch09/아이템-사용')
            return (0,0)
        pending=self.prepare(engine,r)
        if pending is not None:return pending
        return self.commit(engine,r)

    def stock_slots(self, request):return ('held',)

    def supports_physical(self, request):return self.physical

    @abstractmethod
    def prepare(self, engine, request):
        """Check source-specific options; return a pending decision without cost."""

    @abstractmethod
    def commit(self, engine, request):
        """Run the admitted native producer, retaining source-owned receipts."""


class ExtendedIntake(ItemUse):
    physical=True
    silent_refusal=True

    def prepare(self, engine, r):
        if r.selected_move is not None:raise ValueError('selected move requires PP Up')
        if r.shell_batch_id is not None and r.target is not r.user:raise ValueError('only the containing Shuckle eats shell Juice as a Snack')
        if (r.container_selection is not None or r.shell_batch_id is not None) and r.free:raise ValueError('contents use their ordinary Extended intake')
        if r.held_selection is not None:
            if r.target is not r.user:raise ValueError('held food self-use only; giving needs its sourced transfer')
            if r.free:raise ValueError('held food uses its ordinary Extended intake without a cost waiver')
        return None

    def commit(self, engine, r):
        import food_effects as FOOD, state_grants as G
        if r.resumable:
            return FOOD.consume(engine,r.user,r.target,r.source_id,minutes=r.duration_minutes,reason=r.duration_reason,
                count=r.count,accepted=r.accepted,policy=r.food_policy,held_selection=r.held_selection,
                container_selection=r.container_selection,shell_batch_id=r.shell_batch_id,resumable=True,request_id=r.request_id)
        # Time, item stock, recipient history and its effect commit together for
        # quantity stock as well as selected physical items.
        return G.transition(engine,r.user,lambda e,u,t:FOOD.consume(e,u,t,r.source_id,
            minutes=r.duration_minutes,reason=r.duration_reason,count=r.count,
            accepted=r.accepted,policy=r.food_policy,held_selection=r.held_selection,container_selection=r.container_selection,shell_batch_id=r.shell_batch_id),
            participants=(r.target,))


class DrinkUse(ExtendedIntake):
    family=UseFamily.IMMEDIATE


class FoodBuffUse(ExtendedIntake):
    family=UseFamily.STORED_EFFECT


class VitaminUse(ItemUse):
    family=UseFamily.IMMEDIATE
    physical=True

    def prepare(self, engine, r):
        if r.count!=1 or r.duration_minutes is not None or r.duration_reason is not None or r.food_policy is not None:
            raise ValueError('Vitamins use one ordinary item application')

    def commit(self, engine, r):
        import vitamin_moves as V
        return V.consume(engine,r.user,r.target,r.source_id,selected_move=r.selected_move,
                         selected_stat=r.selected_stat,owner_consent_by=r.owner_consent_by,
                         free=r.free,held_selection=r.held_selection)


class LifetimeEffectUse(ItemUse):
    family=UseFamily.IMMEDIATE
    physical=True

    def prepare(self, engine, r):
        if r.count!=1 or r.duration_minutes is not None or r.duration_reason is not None or r.food_policy is not None or r.selected_move is not None:
            raise ValueError('lifetime effects use one ordinary item application')

    def commit(self, engine, r):
        import lifetime_consumables as L
        return L.consume(engine,r.user,r.target,r.source_id,free=r.free,held_selection=r.held_selection)


class GemUse(ItemUse):
    family=UseFamily.STORED_EFFECT
    physical=True

    def stock_slots(self,r):
        import gem_effects as GEM
        return GEM.slots(r.user)

    def prepare(self,engine,r):
        if r.target is not r.user:raise ValueError('a Type Gem empowers its actual user')
        if r.count!=1 or any(x is not None for x in (r.duration_minutes,r.duration_reason,r.food_policy,r.selected_move,r.container_selection,r.shell_batch_id)):raise ValueError('Type Gems use one Free Action item application')

    def commit(self,engine,r):
        import gem_effects as GEM
        return GEM.consume(engine,r.user,r.source_id,held_selection=r.held_selection)


class MushroomUse(ItemUse):
    family=UseFamily.IMMEDIATE
    physical=True
    silent_refusal=True

    def prepare(self, engine, r):
        import herb_mushroom_rules as HERB
        return HERB.prepare_use(engine,r)

    def commit(self, engine, r):
        import herb_mushroom_rules as HERB
        return HERB.consume(engine,r)


class BandageUse(ItemUse):
    family=UseFamily.DEPLOYED
    physical=True

    def prepare(self, engine, r):
        if r.selected_move is not None:raise ValueError('selected move requires PP Up')
        if r.food_policy is not None or r.free:raise ValueError('bandages use their ordinary Extended application')
        if r.duration_minutes is None or r.duration_reason is None:
            return C.PendingDecision('GM Extended bandage application duration')

    def commit(self, engine, r):
        import bandages as B
        return B.apply(engine,r.user,target=r.target,item=r.source_id.split('/',1)[1],
            count=r.count,minutes=r.duration_minutes,reason=r.duration_reason,
            accepted=r.accepted,held_selection=r.held_selection,resumable=r.resumable,request_id=r.request_id)


class ImmediateUse(ItemUse):
    family=UseFamily.IMMEDIATE

    def supports_physical(self, r):
        import restorative_items as R
        return r.source_id in R.HELD_CONSUMABLES

    def prepare(self, engine, r):
        if r.selected_move is not None:raise ValueError('selected move requires PP Up')
        if r.food_policy is not None:raise ValueError('food source policy requires a supported food item')

    def commit(self, engine, r):
        import items as I
        before_actions = len(getattr(r.user, '_action_history', []))
        result = I._use_immediate_item(engine,r.user,r.item_name,r.target,free=r.free,
            accepted=r.accepted,duration_minutes=r.duration_minutes,
            duration_reason=r.duration_reason,count=r.count,held_selection=r.held_selection,
            medicine_source_choice=r.medicine_source_choice)
        if len(getattr(r.user, '_action_history', [])) > before_actions:
            import class_actor_state_actions as CLASS_STATE_ACTIONS
            CLASS_STATE_ACTIONS.observe_healing_item_used(
                engine, r.user, r.target, r.item_name, result
            )
        return result


class AttackUse(ItemUse):
    family=UseFamily.IMMEDIATE
    physical=True
    requires_acceptance=False

    def prepare(self,engine,r):
        import item_attacks as ATTACK
        return ATTACK.prepare(engine,r)

    def commit(self,engine,r):
        import item_attacks as ATTACK
        return ATTACK.consume(engine,r)


class CaltropsUse(ItemUse):
    family=UseFamily.DEPLOYED
    physical=True
    requires_acceptance=False

    def prepare(self,engine,r):
        import caltrops_items as CALTROPS
        return CALTROPS.prepare(engine,r)

    def commit(self,engine,r):
        import caltrops_items as CALTROPS
        return CALTROPS.consume(engine,r)


class SmokeBallUse(ItemUse):
    family=UseFamily.DEPLOYED
    physical=True
    requires_acceptance=False

    def execute(self,engine,r):
        # Observe only valid actual users/stock/placement before any native
        # can_act refusal can write a log. The shared template still owns use.
        pending=self.prepare(engine,r)
        return pending if pending is not None else super().execute(engine,r)

    def prepare(self,engine,r):
        import smoke_balls as SMOKE
        return SMOKE.prepare(engine,r)

    def commit(self,engine,r):
        import smoke_balls as SMOKE
        return SMOKE.consume(engine,r)


class RepelUse(ItemUse):
    family=UseFamily.STORED_EFFECT
    physical=True
    requires_acceptance=False

    def prepare(self,engine,r):
        import repels as REPELS
        return REPELS.prepare(engine,r)

    def commit(self,engine,r):
        import repels as REPELS
        return REPELS.consume(engine,r)


class MagicFluteUse(ItemUse):
    family=None  # Reusable instruments do not have a consumable lifetime.
    physical=True
    requires_acceptance=False

    def prepare(self,engine,r):
        import magic_flute as FLUTE
        return FLUTE.prepare(engine,r)

    def commit(self,engine,r):
        import magic_flute as FLUTE
        return FLUTE.consume(engine,r)


class UnclassifiedUse(ImmediateUse):
    """Keep the existing source interpreter without inventing a reviewed family."""
    family=None


ATTACK=AttackUse()
CALTROPS=CaltropsUse()
SMOKE_BALL=SmokeBallUse()
MAGIC_FLUTE=MagicFluteUse()
REPEL=RepelUse()
DRINK=DrinkUse()
FOOD=FoodBuffUse()
VITAMIN=VitaminUse()
LIFETIME=LifetimeEffectUse()
BANDAGE=BandageUse()
MUSHROOM=MushroomUse()
GEM=GemUse()
IMMEDIATE=ImmediateUse()
UNCLASSIFIED=UnclassifiedUse()


def adapter_for(source_id) -> UseAdapter[UseRequest]:
    import food_effects as F,vitamin_moves as V,restorative_items as R
    import lifetime_consumables as L
    import item_attacks as ATTACKS
    import caltrops_items as TOOLS
    import magic_flute as FLUTE
    import smoke_balls as SMOKE
    import repels as REPELS
    import herb_mushroom_rules as HERB
    if source_id in HERB.MUSHROOMS:return MUSHROOM
    if source_id in REPELS.SOURCES:return REPEL
    if source_id in SMOKE.SOURCES:return SMOKE_BALL
    if source_id in FLUTE.SOURCES:return MAGIC_FLUTE
    if source_id in TOOLS.SOURCES:return CALTROPS
    if source_id in ATTACKS.SOURCES:return ATTACK
    if source_id in ('item/'+t+'주얼' for t in __import__('items').TYPES):return GEM
    if source_id in L.ITEMS:return LIFETIME
    if source_id in V.ALL_ITEMS|{V.SUPPRESSANT}:return VITAMIN
    if source_id in ('item/붕대','item/파스'):return BANDAGE
    if source_id in F.DRINKS:return DRINK
    if F.handles(source_id):return FOOD
    if source_id in R.HELD_CONSUMABLES:return IMMEDIATE
    return UNCLASSIFIED


def dispatch(engine,user,item_name,target=None,**options):
    import csv_item_food_contracts as CSV
    import food_effects as FOOD_EFFECTS
    food_policy=options.get('food_policy')
    if food_policy is not None and type(food_policy) not in (str,dict):
        raise ValueError('named food policy or scoped refreshment decision required')
    source_selection=None
    if type(food_policy) is str and food_policy not in FOOD_EFFECTS.BABY_POLICIES:
        row=__import__('csv_item_contract_policy').definition(engine.r,clause_id=food_policy)
        if row is None or row.get('domain')!='food' or row.get('item_id') not in CSV.ITEM_KINDS:raise ValueError('exact reviewed CSV food clause selection required')
        source_selection=CSV.source_choice(engine.r,row['item_id'],food_policy)
        header=CSV.selected_header(engine.r,source_selection,item_name)
    else:
        header=engine.r.item_effects(item_name)[1]
    uid=header.get('id')
    if type(food_policy)is dict and uid not in FOOD_EFFECTS.DRINKS:
        raise ValueError('scoped refreshment decision requires an actual drink')
    if source_selection is None:source_selection=CSV.intake_choice(engine.r,uid,None if uid in FOOD_EFFECTS.DRINKS else food_policy)
    request=UseRequest(user=user,target=target or user,item_name=item_name,source_id=uid,source_selection=source_selection,**options)
    adapter=adapter_for(uid)
    category=header.get('battle_tool')
    if category is not None and adapter is UNCLASSIFIED:
        # A category is not permission to spend an inert item.  In particular,
        # the reusable flute and placed/attached/burned tag need their own use
        # mode, rather than the ordinary immediate-item stock debit.
        return C.PendingDecision('Battle tool needs its source-specific use adapter',
            basis={'source':uid,'catalog':category,'status':'unimplemented_battle_tool_use'})
    return adapter.execute(engine,request)

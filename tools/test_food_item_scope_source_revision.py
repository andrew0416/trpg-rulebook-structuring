"""Food eligibility and encounter-scoped, explicitly sourced medicine use."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json, random, sys, unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon, build_trainer
from engine import Rules, Engine, Combatant
from grid import Grid
import ability_state_projection as PROJECTION
import consumption_execution as EXECUTION
import downtime as D
import food_effects as FOOD
import native_rule_policy as POLICY
import native_scenario_fixture as NATIVE
import temporary_hp as TEMP
import turn as TURN


class FoodItemScopeSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def world(self):
        e=Engine(self.r,701);e.grid=Grid(30,30)
        a=Combatant(self.r,build_trainer(self.r,'medicine-user',30,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
            skills={'의학':'초보'},moves=[],abilities=[],pos=(1,1),extra={'items':{},'edges':[]}))
        p=Combatant(self.r,build_pokemon(self.r,'이브이',30,moves=[],abilities=[],pos=(2,1),
            extra={'items':{},'trainer_id':a.entity_id}))
        for c in (a,p):e.gm.add_combatant(c,reason='actual medicine participants')
        return e,a,p

    def choice(self,variant):
        if variant is None:return None
        pending=POLICY.medicine_source_choices(self.r)
        self.assertEqual(pending['status'],'PolicyInputsRequired')
        return {'value':variant,'reason':'GM chose the printed medicine action source',
                'scope':pending['decision_scope']}

    def restore(self,e):
        loaded=Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        self.assertTrue(loaded.validate_state()['valid'])
        return loaded,{c.entity_id:c for c in loaded.everyone}

    def stock(self,actor,item,count=1):
        inventory=actor.spec.setdefault('items',{})
        inventory[item]=inventory.get(item,0)+count

    def snack(self,e,c):
        self.stock(c,'초코바')
        return e.use_item(c,'초코바',duration_minutes=1,duration_reason='observed one-minute snack intake')

    def herb(self,e,c):
        self.stock(c,'힘의가루')
        self.assertEqual(e.use_item(c,'힘의가루'),(1,0))

    def form_world(self,source):
        e=Engine(self.r,701);e.grid=Grid(30,30)
        power=source=='ability/스웜체인지'
        species='지가르데 50%폼' if power else '약어리 단독의 모습'
        other_species='지가르데 퍼펙트폼' if power else '약어리 군집의 모습'
        original,active=('50%폼','퍼펙트폼') if power else ('단독의모습','군집의모습')
        base=build_pokemon(self.r,species,30,abilities=[source],moves=['move/몸통박치기'],pos=(2,2),extra={'items':{}})
        other=build_pokemon(self.r,other_species,30,abilities=[source],moves=['move/몸통박치기'])
        c=Combatant(self.r,base);e.gm.add_combatant(c,reason='actual form ability recipient')
        if power:
            plans={name:{key:deepcopy(spec['initial_allocation'][key]) for key in ('species_base','investment')}
                   for name,spec in ((original,base),(active,other))}
            e.configure_growth_forms(c,plans,active=original,source=source)
        else:
            # Schooling requires shared HP; use the recipient's actual HP allocation.
            school=deepcopy(other['stats']);school['hp']=base['stats']['hp']
            e.configure_form_allocations(c,{original:deepcopy(base['stats']),active:school},active=original,source=source)
        e.start_round([c]);e.start_of_turn(c,initiative_count=20)
        if power:c.hp=(c.base_max_hp-1)//2
        e.activate_ability_state(c,source,choice=active,reason='actual daily form ability')
        self.assertEqual(c.form,active);self.assertTrue(PROJECTION.temp_hp_blocked(c))
        e.end_of_turn(c);e.end_encounter([c],round_elapsed_seconds=0)
        return e,c,active

    def spend_save_buff(self,e,c,buff_id):
        e.apply_status(c,'마비')
        e.consume_food_buff(c,buff_id=buff_id,save_condition='마비')
        seed=next(seed for seed in range(1000) if random.Random(seed).randint(1,20)==9)
        e.rng.seed(seed);e.start_round([c]);e.start_of_turn(c,initiative_count=20)
        self.assertIsNone(c._turn_action_limit)
        self.assertFalse(c.buffs)
        self.assertEqual(c.spec['food_consumption_receipts'][-1]['benefit'],{'save_condition':'마비','bonus':2})
        e.cure_status(c,'마비');e.end_of_turn(c);e.end_encounter([c],round_elapsed_seconds=0)

    def test_real_schooling_and_power_construct_allow_first_herb_save_and_snack_but_not_external_temp_hp(self):
        for source in ('ability/어군','ability/스웜체인지'):
            with self.subTest(source=source):
                e,c,active=self.form_world(source)
                before=c.temp_hp
                self.assertEqual(TEMP.grant(e,c,before+20,provenance={'source':'other/source'}),0)
                self.herb(e,c)
                self.assertEqual((c.form,c.temp_hp),(active,before))
                buff=deepcopy(c.buffs[0])
                self.assertEqual(buff['effect'],{'kind':'save_bonus','amount':2})
                self.assertEqual(FOOD.herbal_state(c)['uses'][0]['buff_id'],buff['id'])
                loaded,actors=self.restore(e);saved=actors[c.entity_id]
                self.assertEqual(saved.buffs[0],buff)
                self.assertTrue(PROJECTION.temp_hp_blocked(saved))
                self.spend_save_buff(loaded,saved,buff['id'])
                start=loaded.elapsed_seconds;out=self.snack(loaded,saved)
                self.assertEqual(loaded.elapsed_seconds-start,60)
                self.assertEqual(saved.spec['items']['초코바'],0)
                self.assertEqual(FOOD.get_buff(saved,out['buff_id'])['effect'],{'kind':'heal','amount':5})
                hp=saved.hp;loaded.consume_food_buff(saved,buff_id=out['buff_id'],action_kind='free',action_reason='actual snack activation')
                self.assertEqual(saved.hp,min(saved.max_hp,hp+5));self.assertFalse(saved.buffs)
                self.assertEqual(TEMP.grant(loaded,saved,saved.temp_hp+20),0)
                self.assertEqual(FOOD.herbal_state(saved)['count'],1)
                self.assertTrue(loaded.validate_state()['valid'])

    def test_second_herb_blocks_food_in_both_forms_until_actual_extended_rest_after_restore(self):
        for source in ('ability/어군','ability/스웜체인지'):
            with self.subTest(source=source):
                e,c,_=self.form_world(source);self.herb(e,c)
                self.spend_save_buff(e,c,c.buffs[0]['id']);self.herb(e,c)
                self.assertEqual(FOOD.herbal_state(c)['count'],2)
                self.assertEqual(TEMP.grant(e,c,c.temp_hp+20),0)
                self.stock(c,'초코바');loaded,actors=self.restore(e);saved=actors[c.entity_id]
                NATIVE.assert_rejected_unchanged(loaded,lambda:loaded.use_item(saved,'초코바',
                    duration_minutes=1,duration_reason='second herb still blocks food'),reason_pattern='cannot gain another Digestion Buff')
                D.rest(loaded,saved,239,rest_id='actual-food-rest')
                self.assertEqual(FOOD.herbal_state(saved)['count'],2)
                D.rest(loaded,saved,1,rest_id='actual-food-rest')
                self.assertEqual(FOOD.herbal_state(saved)['count'],0)
                out=loaded.use_item(saved,'초코바',duration_minutes=1,duration_reason='food after actual Extended Rest')
                self.assertEqual(saved.buffs[0]['id'],out['buff_id'])
                self.assertEqual(saved.spec['items']['초코바'],0)
                self.assertTrue(loaded.validate_state()['valid'])

    def test_outside_medicine_and_x_never_create_next_encounter_debt_with_or_without_spent_prior_budget(self):
        for prior in (False,True):
            for variant in (None,'korean_swift','english_shift'):
                for item,self_use in (('상처약',False),('상처약',True),('플러스파워',True)):
                    with self.subTest(prior=prior,variant=variant,item=item,self_use=self_use):
                        e,a,p=self.world();user=p if self_use else a;target=p
                        if prior:
                            e.start_round([a,p]);e.start_of_turn(user,initiative_count=20)
                            for kind in ('standard','shift','swift'):self.assertTrue(TURN.spend(e,user,kind,'actual preceding combat action'))
                            e.end_of_turn(user);e.end_encounter([a,p],round_elapsed_seconds=0)
                        budget={key:deepcopy(vars(user)[key]) for key in ('budget',) if key in vars(user)}
                        debt={key:deepcopy(vars(target)[key]) for key in ('pending_action_loss',) if key in vars(target)}
                        history=deepcopy(user._action_history) if hasattr(user,'_action_history') else []
                        self.stock(user,item,3);choice=self.choice(variant)
                        for n in range(3):
                            target.hp=1
                            self.assertEqual(e.use_item(user,item,target,medicine_source_choice=choice),(1,0))
                            if item=='상처약':self.assertEqual(target.hp,21)
                            else:self.assertEqual(target.stages['atk'],min(6,2*(n+1)))
                            self.assertEqual({key:vars(user)[key] for key in budget},budget)
                            self.assertEqual('budget' in vars(user),'budget' in budget)
                            self.assertEqual({key:vars(target)[key] for key in ('pending_action_loss',) if key in vars(target)},debt)
                        self.assertEqual(user.spec['items'][item],0)
                        self.assertEqual(user._action_history[:len(history)],history)
                        self.assertEqual(len(user._action_history)-len(history),3)
                        receipts=EXECUTION.validate(user)
                        self.assertEqual(len(receipts),3)
                        for receipt in receipts.values():
                            medicine=receipt['item_stock']['medicine_policy']
                            self.assertEqual(medicine['source_variant'],variant or 'korean_swift')
                            self.assertFalse(medicine['encounter_active'])
                            if variant:self.assertEqual(medicine['source_policy']['decision_evidence'][0]['scope'],choice['scope'])
                        e.gm.restore(e.gm.snapshot());loaded,actors=self.restore(e)
                        a,p=actors[a.entity_id],actors[p.entity_id]
                        loaded.start_round([a,p])
                        for actor in (a,p):
                            loaded.start_of_turn(actor,initiative_count=20)
                            self.assertEqual(actor.budget,{'standard':1,'shift':1,'swift':1})
                            self.assertIsNone(actor.pending_action_loss);loaded.end_of_turn(actor)

    def test_explicit_kr_and_en_retain_distinct_combat_debt_and_shared_medic_self_and_x_rules(self):
        for variant,lost in (('korean_swift','swift'),('english_shift','shift')):
            for item,self_use,medic in (('상처약',False,False),('플러스파워',False,False),
                                      ('상처약',False,True),('플러스파워',False,True),
                                      ('상처약',True,False),('플러스파워',True,False)):
                with self.subTest(variant=variant,item=item,self_use=self_use,medic=medic):
                    e,a,p=self.world();user=p if self_use else a;target=p
                    if medic:a.spec['edges']=['edge/메딕-훈련']
                    self.stock(user,item);target.hp=1
                    e.start_round([a,p]);e.start_of_turn(user,initiative_count=20)
                    prior_debt={key:deepcopy(vars(target)[key]) for key in ('pending_action_loss',) if key in vars(target)}
                    self.assertEqual(e.use_item(user,item,target,medicine_source_choice=self.choice(variant)),(1,0))
                    self.assertEqual(user.budget,{'standard':0,'shift':0 if self_use and item=='상처약' else 1,'swift':1})
                    expected=None if medic or (self_use and item=='상처약') else {'standard':1,lost:1}
                    if expected is None:
                        self.assertEqual({key:vars(target)[key] for key in ('pending_action_loss',) if key in vars(target)},prior_debt)
                    else:self.assertEqual(target.pending_action_loss,expected)
                    if item=='상처약':self.assertEqual(target.hp,21)
                    else:self.assertEqual(target.stages['atk'],2)
                    e.end_of_turn(user)
                    if self_use:e.start_round([p])
                    e.start_of_turn(target,initiative_count=20)
                    next_budget={'standard':1,'shift':1,'swift':1}
                    if expected:
                        for key in expected:next_budget[key]=0
                    self.assertEqual(target.budget,next_budget)
                    self.assertIsNone(target.pending_action_loss)

    def test_source_choice_rejects_wrong_scope_unrelated_food_and_stale_english_before_cost(self):
        e,a,p=self.world();self.stock(a,'상처약');self.stock(a,'초코바')
        choice=self.choice('english_shift');bad=deepcopy(choice);bad['scope']['profile_hash']='wrong'
        NATIVE.assert_rejected_unchanged(e,lambda:e.use_item(a,'상처약',p,medicine_source_choice=bad),reason_pattern='scope changed')
        NATIVE.assert_rejected_unchanged(e,lambda:e.use_item(a,'초코바',p,duration_minutes=1,
            duration_reason='unrelated food',medicine_source_choice=choice),reason_pattern='requires a restorative or X item')
        original=Path.read_bytes
        def changed(path):
            raw=original(path)
            return raw+b'changed' if path.name=='core-1.05-medicine.txt' else raw
        with patch.object(Path,'read_bytes',changed):
            NATIVE.assert_rejected_unchanged(e,lambda:e.use_item(a,'상처약',p,medicine_source_choice=choice),reason_pattern='source changed')
        before=e.export_state()
        self.assertEqual(e.use_item(a,'상처약',p,medicine_source_choice=choice,accepted=False),(0,0))
        self.assertEqual(e.export_state(),before)

    def test_outside_payment_keeps_status_and_open_combat_turn_permissions(self):
        for status in ('잠듦','얼음'):
            e,a,p=self.world();self.stock(a,'상처약');e.apply_status(a,status);before=e.export_state()
            self.assertEqual(e.use_item(a,'상처약',p),(0,0));self.assertEqual(e.export_state(),before)
        e,a,p=self.world();self.stock(a,'상처약');e.begin_encounter([a,p]);before=e.export_state()
        self.assertEqual(e.use_item(a,'상처약',p),(0,0));self.assertEqual(e.export_state(),before)
        e.start_round([a,p]);e.start_of_turn(a,initiative_count=20)
        self.assertTrue(TURN.spend(e,a,'standard','actual earlier action'));before=e.export_state()
        self.assertEqual(e.use_item(a,'상처약',p),(0,0));self.assertEqual(e.export_state(),before)


if __name__=='__main__':unittest.main()

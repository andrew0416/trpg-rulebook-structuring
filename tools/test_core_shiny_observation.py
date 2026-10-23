"""C11-043: observed cosmetic specimen -> native introduction and funded trade."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from contest import ContestRules, ContestEngine, Contestant
import cosmetic_specimen as SHINY
import pokemon_party as PARTY
import campaign_rewards as MONEY


class ShinyObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')
        cls.cr = ContestRules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 43)
        self.a = self.add(build_trainer(self.r, 'specimen owner', 5,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
            skills={'매력':3}, abilities=[], extra={'money':50}))
        self.b = self.add(build_trainer(self.r, 'collector', 5,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
            skills={'매력':3}, abilities=[], extra={'money':1000}))
        self.p = self.add(build_pokemon(self.r,'브케인',5,moves=[],abilities=[],
            extra={'trainer_id':self.a.entity_id}))
        self.q = self.add(build_pokemon(self.r,'브케인',5,moves=[],abilities=[],
            extra={'trainer_id':self.a.entity_id}))
        PARTY.configure(self.e,self.a,mode='standard',roster=[self.p,self.q],
            storage={'kind':'center','id':'PC-A'},reason='established actual ownership')
        PARTY.configure(self.e,self.b,mode='standard',roster=[],
            storage={'kind':'center','id':'PC-B'},reason='established actual buyer')
        self.ce = ContestEngine(self.cr,43)

    def add(self,spec):
        c=Combatant(self.r,spec);self.e.gm.add_combatant(c);return c

    def observe(self,**kw):
        values=dict(description='silver outer fur',introduction_bonus=True,
            reason='GM adopts cosmetic coloration only');values.update(kw)
        return SHINY.observe(self.e,self.p,**values)

    def declare(self,*,pokemon=None,owner=None,choices=None):
        return self.ce.contestant_from_combatants(self.e,pokemon or self.p,owner or self.a,
            '매력',{},bonus_stats={SHINY.SOURCE:'아름다움'} if choices is None else choices)

    def sale(self,**kw):
        values=dict(ordinary_value=100,agreed_value=175,
            agreement='GM and both parties agree this individual is worth 175 vs ordinary 100 points',
            reason='observed funded specimen money trade',request_id='shiny-sale')
        values.update(kw)
        return SHINY.settle_money_sale(self.e,self.a,self.p,self.b,**values)

    def snapshot(self):return deepcopy(self.e.export_state())

    def raw_snapshot(self):
        # Deliberately malformed owner/source fixtures cannot be exported.
        return deepcopy(([(x.entity_id,{k:v for k,v in vars(x).items() if k!='r'})
            for x in self.e.everyone],self.e.rng.getstate(),self.e.log_lines,
            self.e.elapsed_seconds,getattr(self.e,'_world_relation_receipts',{})))

    def test_observation_is_individual_and_preserves_species_growth_and_learning(self):
        before=deepcopy({k:v for k,v in vars(self.p).items() if k!='r'})
        species=deepcopy(self.r.species);learnsets=deepcopy(self.r.learnsets)
        row=self.observe()
        after=deepcopy({k:v for k,v in vars(self.p).items() if k!='r'});after['spec'].pop(SHINY.KEY)
        self.assertEqual(before,after)
        self.assertEqual(self.r.species,species);self.assertEqual(self.r.learnsets,learnsets)
        self.assertIsNone(SHINY.read(self.e,self.q))
        row['description']='detached';self.assertEqual(SHINY.read(self.e,self.p)['description'],'silver outer fur')
        self.assertEqual(SHINY.read(self.e,self.p)['actor_id'],self.p.entity_id)

    def test_native_introduction_rolls_two_actual_dice_in_selected_stat_once(self):
        self.observe();c=self.declare();expected=deepcopy(self.ce.rng)
        ordinary=[expected.randint(1,6) for _ in range(3)]
        extra=[expected.randint(1,6) for _ in range(2)]
        self.ce.intro_stage([c],'귀여움')
        self.assertEqual(self.ce.rng.getstate(),expected.getstate())
        self.assertEqual(c.stat_dice,{'귀여움':sum(x>=3 for x in ordinary),'아름다움':sum(x>=3 for x in extra)})
        self.assertTrue(any(SHINY.SOURCE in line and '2d6' in line for line in self.ce.log_lines))
        before=deepcopy((vars(c),self.ce.log_lines,self.ce.rng.getstate()))
        with self.assertRaises(ValueError):self.ce.intro_stage([c],'귀여움')
        self.assertEqual((vars(c),self.ce.log_lines,self.ce.rng.getstate()),before)

    def test_optional_adoption_and_decline_leave_ordinary_introduction_unchanged(self):
        for adopted,choice in ((False,False),(True,False),(True,True)):
            with self.subTest(adopted=adopted,choice=choice):
                self.setUp()
                if adopted:self.observe(introduction_bonus=choice)
                c=self.declare(choices={});expected=deepcopy(self.ce.rng)
                faces=[expected.randint(1,6) for _ in range(3)]
                self.ce.intro_stage([c],None)
                self.assertEqual(c.stat_dice,{'귀여움':sum(x>=3 for x in faces)})
                self.assertEqual(self.ce.rng.getstate(),expected.getstate())
                if not choice:
                    with self.assertRaises(ValueError):self.declare()

    def test_forged_foreign_and_stale_introduction_reject_before_rng(self):
        self.observe();c=self.declare()
        self.q.spec[SHINY.KEY]=deepcopy(self.p.spec[SHINY.KEY])
        with self.assertRaises(ValueError):self.declare(pokemon=self.q)
        self.q.spec.pop(SHINY.KEY)
        naked=Contestant('caller-only shiny',{},[],'매력',3,'귀여움',
            intro_sources=[SHINY.SOURCE],intro_bonuses=[{'source_id':SHINY.SOURCE,'stat':'아름다움','dice':2}])
        before=self.ce.rng.getstate()
        with self.assertRaises(ValueError):self.ce.intro_stage([naked],None)
        self.assertEqual(self.ce.rng.getstate(),before)
        for change in ('decline','owner','count','stat','source'):
            with self.subTest(change=change):
                self.observe();c=self.declare();saved=deepcopy(self.p.spec)
                before=deepcopy((vars(c),self.ce.log_lines,self.ce.rng.getstate()))
                if change=='decline':self.p.spec[SHINY.KEY]['introduction_bonus']=False
                elif change=='owner':self.p.spec['trainer_id']=self.b.entity_id
                elif change=='count':c.intro_bonuses[0]['dice']=3;before=deepcopy((vars(c),self.ce.log_lines,self.ce.rng.getstate()))
                elif change=='stat':c.intro_bonuses[0]['stat']='unknown';before=deepcopy((vars(c),self.ce.log_lines,self.ce.rng.getstate()))
                original=self.r._selected_rule
                with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**options: 'unselected' if change=='source' and uid==SHINY.SOURCE else original(uid,**options)):
                    with self.assertRaises(ValueError):self.ce.intro_stage([c],None)
                self.assertEqual((vars(c),self.ce.log_lines,self.ce.rng.getstate()),before)
                self.p.spec=saved

    def test_actual_higher_money_trade_commits_native_title_and_payment_once(self):
        self.observe();specimen=deepcopy(SHINY.read(self.e,self.p));stats=deepcopy(self.p.stats)
        row=self.sale()
        self.assertEqual((self.a.spec['money'],self.b.spec['money']),(225,825))
        self.assertNotIn(self.p.entity_id,self.a.spec['pokemon_registry'])
        self.assertEqual(self.b.spec['pokemon_registry'][self.p.entity_id]['owner_id'],self.b.entity_id)
        self.assertEqual(self.p.spec['trainer_id'],self.b.entity_id)
        self.assertEqual(self.p.stats,stats);self.assertEqual(SHINY.read(self.e,self.p),specimen)
        self.assertEqual(row['settlement']['agreed_value'],175)
        self.assertEqual(set(self.e._world_relation_receipts),{'shiny-sale'})
        before=self.snapshot();self.assertEqual(self.sale(),row);self.assertEqual(self.snapshot(),before)
        with self.assertRaises(ValueError):self.sale(agreed_value=176)
        self.assertEqual(self.snapshot(),before)
        # The new current owner can use the same individual cosmetic fact.
        c=self.declare(owner=self.b);self.ce.intro_stage([c],None);self.assertTrue(c.intro_completed)

    def test_trade_requires_explicit_higher_agreement_actual_funds_and_actual_specimen(self):
        self.observe()
        invalid=[dict(ordinary_value=-1),dict(ordinary_value=True),dict(agreed_value=True),
            dict(agreed_value=100),dict(agreed_value=99),dict(agreed_value=1001),
            dict(agreed_value=175.5),dict(agreement=''),dict(reason=''),dict(request_id='')]
        before=self.snapshot()
        for options in invalid:
            with self.subTest(options=options),self.assertRaises(ValueError):self.sale(**options)
            self.assertEqual(self.snapshot(),before)
        for change in ('unobserved','wrong-placement','clone','bad-source','bad-hash'):
            with self.subTest(change=change):
                saved=deepcopy(self.p.spec)
                if change=='unobserved':self.p.spec.pop(SHINY.KEY)
                elif change=='wrong-placement':self.p.spec['party_location']['owner_id']='other'
                elif change=='clone':self.p.spec[SHINY.KEY]['actor_id']=self.q.entity_id
                original=self.r._selected_rule
                ref={**SHINY.REFERENCE,'sha256':'0'*64} if change=='bad-hash' else SHINY.REFERENCE
                before=self.raw_snapshot()
                with patch.object(SHINY,'REFERENCE',ref),patch.object(self.r,'_selected_rule',side_effect=lambda uid,**options: 'unselected' if change=='bad-source' and uid==SHINY.SOURCE else original(uid,**options)):
                    with self.assertRaises(ValueError):self.sale()
                self.assertEqual(self.raw_snapshot(),before);self.p.spec=saved
        impostor=Combatant(self.r,deepcopy(self.p.spec))
        with self.assertRaises(ValueError):SHINY.observe(self.e,impostor,description='silver',introduction_bonus=True,reason='not actual')

    def test_late_payment_failure_rolls_back_native_transfer_and_both_balances(self):
        self.observe();before=self.snapshot();pay=MONEY.pay
        def failure(actor,**options):
            if actor.entity_id==self.a.entity_id:raise ValueError('late actual seller settlement failure')
            return pay(actor,**options)
        with patch.object(MONEY,'pay',side_effect=failure):
            with self.assertRaisesRegex(ValueError,'late actual seller'):self.sale()
        self.assertEqual(self.snapshot(),before)
        self.sale();self.assertEqual((self.a.spec['money'],self.b.spec['money']),(225,825))

    def test_snapshot_and_json_restore_preserve_observation_and_native_settlement_replay(self):
        self.observe();self.e.gm.snapshot('shiny')
        self.observe(description='revised silver pattern',introduction_bonus=False)
        self.e.gm.restore('shiny');self.assertEqual(SHINY.read(self.e,self.p)['description'],'silver outer fur')
        row=self.sale();ids=[x.entity_id for x in (self.a,self.b,self.p,self.q)]
        self.e=Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state())))
        actors={x.entity_id:x for x in self.e.everyone};self.a,self.b,self.p,self.q=[actors[x] for x in ids]
        self.assertEqual(self.sale(),row);self.assertEqual((self.a.spec['money'],self.b.spec['money']),(225,825))
        self.ce=ContestEngine(self.cr,43);c=self.declare(owner=self.b)
        self.ce.intro_stage([c],None);self.assertTrue(c.intro_completed)

    def test_completed_sale_replay_rechecks_current_owner_and_selected_source(self):
        self.observe();self.sale();before=self.snapshot();original=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid:'unselected' if uid==SHINY.SOURCE else original(uid)):
            with self.assertRaises(ValueError):self.sale()
        self.assertEqual(self.snapshot(),before)
        PARTY.transfer(self.e,self.b,target=self.p,new_owner=self.a,reason='later actual return',request_id='return')
        before=self.snapshot()
        with self.assertRaises(ValueError):self.sale()
        self.assertEqual(self.snapshot(),before)


if __name__=='__main__':unittest.main()

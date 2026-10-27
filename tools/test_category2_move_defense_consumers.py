"""Independent actual-recipient checks for existing completed consumers."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import passive_events as PASSIVE
import move_defense_reactions as DEFENSE
import move_completion as COMPLETE
import world_entities as WORLD
import test_category2_optional_weapon_framework as WEAPON_TESTS
import test_category2_csv_stellar_tera_blast as STELLAR_TESTS
import test_category2_optional_move_modes as MODE_TESTS
import optional_weapon_framework as WEAPON
import stellar_tera_blast as STELLAR
import optional_move_modes as MODES


class MoveDefenseConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')

    def reactor(self,e,pos,side):
        actor=Combatant(self.rules,build_trainer(self.rules,'recipient',30,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
            extra={'skills':{'육상':5},'movement':{'land':8},'movement_basis':'current',
                   'pos':pos,'side':side,'abilities':[]}))
        e.gm.add_combatant(actor)
        return actor

    def intercept(self,e,a,b,c,move,path,destination):
        e.rng.seed(530)
        e.watch_move_defense(b,[{'actor_id':c.entity_id,'source':DEFENSE.MELEE}],reason='actual recipient consumer')
        with self.assertRaises(PASSIVE.PassiveEventPending):e.use_move(a,b,move,set_damage=True)
        event=e._passive_pending
        e.choose_move_defense(event,c,use=True,options={'path':path,'skill':'육상','mode':'land',
            'shove_destination':destination,'roll_options':{'fixed':[6]*5}},reason='real shared consumer')
        return event

    def test_steelheart_observes_actual_recipient_and_not_displaced_target(self):
        for variant in ('english_incoming_melee','korean_book_outgoing'):
            with self.subTest(variant=variant):
                f=WEAPON_TESTS.OptionalWeaponFrameworkTests();f.r=self.rules
                e,a,b,c=f.fixture(family='physical')
                choice=None
                if variant=='korean_book_outgoing':
                    choice={'value':variant,'reason':'actual outgoing recipient history under the complete Korean definition',
                            'scope':WEAPON.steelheart_source_choices(e)['decision_scope']}
                    WEAPON.select_steelheart_source(e,a,choice)
                f.start(e,a)
                event=self.intercept(e,a,b,c,'move/몸통박치기',[(4,2),(4,3),(3,3),(3,2)],[3,1])
                row=e._move_completions[e._passive_events[event]['completion_id']]
                received=COMPLETE.recipient_result(row,c)
                self.assertIs(received['actor'],c);self.assertEqual(received['original_id'],b.entity_id)
                self.assertIsNone(COMPLETE.recipient_result(row,b))
                child=received['child_event']
                self.assertTrue(COMPLETE.require_hit_return(e,child,c)['result']['hit'])
                with self.assertRaisesRegex(ValueError,'actual successful nonprevented recipient hit required'):
                    COMPLETE.require_hit_return(e,event,b)
                history=a.spec[WEAPON.HITS]
                self.assertEqual((history['policy_variant'],history['source_choice']),(variant,choice))
                self.assertEqual(history['targets'],[c.entity_id] if variant=='korean_book_outgoing' else [])
                self.assertEqual(history['receipts'],[row['id']+':'+c.entity_id])
                before=e.export_state()
                WEAPON.observe_hit(e,row,a,b);WEAPON.observe_hit(e,row,a,c)
                self.assertEqual(e.export_state(),before)
                restored=Engine.import_state(self.rules,before);index=WORLD.actor_index(restored)
                self.assertEqual(index[a.entity_id].spec[WEAPON.HITS],history)
                self.assertTrue(COMPLETE.require_hit_return(restored,child,index[c.entity_id])['result']['hit'])

    def test_stellar_opportunity_uses_actual_recipient_types(self):
        f=STELLAR_TESTS.StellarTeraBlastTests();f.rules=self.rules;f.setUp()
        e,a,b=f.engine,f.owner,f.foe
        c=Combatant(self.rules,build_pokemon(self.rules,'꼬부기',30,name='loyal interceptor',
            moves=['move/몸통박치기'],abilities=[],extra={'side':'wild','pos':(3,5),
                'loyalty':6,'skills':{'육상':5},'movement':{'land':8},'movement_basis':'current'}))
        e.gm.add_combatant(c)
        self.intercept(e,a,b,c,'move/몸통박치기',[(3,5),(3,4),(3,3),(3,2)],[3,1])
        rows=a.spec[STELLAR.STATE]['opportunities']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['target_id'],c.entity_id)
        self.assertEqual(rows[0]['types'],list(c.types))
        Engine.import_state(self.rules,e.export_state())

    def test_stone_axe_optional_hit_and_vortex_belong_to_actual_recipient(self):
        f=MODE_TESTS.OptionalMoveModeTests();f.r=self.rules;f.make_world()
        e,a,b=f.e,f.p,f.t;del e.d20
        c=self.reactor(e,(11,13),'wild')
        f.select('move/암석액스')
        self.intercept(e,a,b,c,'move/암석액스',[(11,13),(11,12),(11,11),(11,10)],[12,10])
        self.assertFalse({'조이기','둔화','수렁'} & b.conditions)
        self.assertTrue({'조이기','둔화','수렁'} <= c.conditions)
        self.assertEqual(MODES.history(a)[0]['use']['boundary'],'hit')
        Engine.import_state(self.rules,e.export_state())


if __name__=='__main__':unittest.main()

"""Attachment lifetime and common injury allowance through native consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_item_stock as _fixture_test_category2_item_stock
import bandages as B,downtime as D,injury_recovery as I,state_codec as CODEC,clock_invocations as CLOCK

class BandageStateTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_item_stock.ItemStockTests.setUpClass.__func__)
 setUp=_fixture_test_category2_item_stock.ItemStockTests.setUp
 add=_fixture_test_category2_item_stock.ItemStockTests.add
 restored=_fixture_test_category2_item_stock.ItemStockTests.restored
 snap=_fixture_test_category2_item_stock.ItemStockTests.snap
 def apply(self,actor,*,count=1,item='붕대'):
  return self.e.use_item(self.a,item,actor,count=count,duration_minutes=1,duration_reason='observed Extended application')
 def test_rest_remainder_lifetime_and_single_recovery_survive_both_restore_paths(self):
  for kind in ('trainer','pokemon'):
   self.setUp();actor=self.a if kind=='trainer' else self.p
   actor.injuries=2;actor.hp=1;self.a.spec['items']={'붕대':2}
   result=self.apply(actor,count=2);self.assertEqual(result['record']['source_id'],'item/붕대')
   D.rest(self.e,actor,29,rest_id='continuous-rest');self.assertEqual(actor.hp,1)
   snapshot=self.e.gm.snapshot();loaded=self.restored();copy=next(c for c in loaded.gm.everyone if c.entity_id==actor.entity_id)
   for engine,target in ((self.e,actor),(loaded,copy)):
    D.rest(engine,target,1,rest_id='continuous-rest');self.assertEqual(target.hp,1+target.base_max_hp//8)
    engine.advance_time(19799,[target]);self.assertEqual(target.injuries,2)
    engine.advance_time(1,[target]);record=B.validate(target)[0]
    self.assertEqual((record['status'],record['ended_at'],record['injuries_healed']),('expired',21660,2))
    self.assertEqual(target.injuries,0);self.assertEqual(I.healed_today(target),2)
    engine.advance_time(21600,[target]);self.assertEqual(I.healed_today(target),2)
   self.e.gm.restore(snapshot);self.assertEqual(actor.hp,1);self.assertEqual(actor.injuries,2)
   self.assertEqual(B.validate(actor)[0]['status'],'active');self.assertEqual(self.a.spec['items']['붕대'],0)
 def test_grouped_recovery_uses_same_daily_cap_as_actual_rest_and_center_after_save(self):
  for kind in ('trainer','pokemon'):
   self.setUp();actor=self.a if kind=='trainer' else self.p;actor.injuries=6
   D.extended_rest(self.e,actor,24);self.assertEqual(actor.injuries,5);self.assertEqual(I.healed_today(actor),1)
   self.a.spec['items']={'붕대':6};self.apply(actor,count=4)
   loaded=self.restored();target=next(c for c in loaded.gm.everyone if c.entity_id==actor.entity_id)
   loaded.advance_time(21600,[target]);self.assertEqual(target.injuries,3);self.assertEqual(I.healed_today(target),3)
   self.assertEqual(B.validate(target)[0]['injuries_healed'],2)
   D.pokemon_center(loaded,target);self.assertEqual(target.injuries,3)
   D.new_day(target);D.pokemon_center(loaded,target)
   self.assertEqual(target.injuries,0);self.assertEqual(I.healed_today(target),3)
   loaded.advance_time(21600,[target]);self.assertEqual(I.healed_today(target),3)
 def test_inconsistent_attachment_never_advances_rests_spends_or_exports(self):
  self.a.spec['items']={'붕대':3};self.apply(self.p);baseline=deepcopy(self.p.spec)
  mutations=[lambda r:r.update(count=True),lambda r:r.update(count=2),lambda r:r.update(expires_at=21661),lambda r:r.update(item='상처약'),lambda r:r.update(source_id='item/파스'),lambda r:r.update(status='expired'),lambda r:r.update(ended_at=60),lambda r:r.update(gap_count=False)]
  for mutate in mutations:
   self.p.spec.clear();self.p.spec.update(deepcopy(baseline));mutate(self.p.spec['bandages'][0]);before=self.snap()
   for action in (lambda:self.apply(self.p),lambda:self.e.advance_time(21600),lambda:D.rest(self.e,self.p,30),self.e.export_state):
    with self.assertRaises(ValueError):action()
    self.assertEqual(self.snap(),before)
  # Construct the intentionally corrupt save; real load still runs both validators.
  with patch.object(B,'validate',return_value=[]),patch.object(CLOCK,'validate',return_value=True):payload=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
  self.assertEqual(self.snap(),before)
 def test_unknown_elapsed_interval_remains_explicit_after_durable_restore(self):
  self.p.injuries=1;self.a.spec['items']={'붕대':1};self.apply(self.p)
  self.e.unresolved_time_intervals.append({'reason':'observed travel with unknown duration'})
  self.e.advance_time(21601);self.assertEqual(self.p.injuries,1)
  loaded=self.restored();target=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  record=B.validate(target)[0];self.assertEqual(record['status'],'active');self.assertIn('timing_pending',record)
  B.resolve_timing(loaded,target,target=target,bandage_id=record['id'],remaining_seconds=0,reason='GM observed six hours elapsed')
  self.assertEqual(target.injuries,0);self.assertEqual(B.validate(target)[0]['status'],'expired')
  payload=CODEC.dump_engine(loaded);again=CODEC.load_engine(self.r,payload)
  actor=next(c for c in again.gm.everyone if c.entity_id==target.entity_id)
  again.advance_time(21600);self.assertEqual(I.healed_today(actor),1)

if __name__=='__main__':unittest.main()

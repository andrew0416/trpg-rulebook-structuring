"""Direct vehicle attack-type boundary for the six-file restoration candidate."""
import unittest

import test_category2_vehicle_native as FIX
import type_state as TYPES


class VehicleAttackBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(FIX.NativeVehicleTests.setUpClass.__func__)
    trainer = FIX.NativeVehicleTests.trainer
    setUp = FIX.NativeVehicleTests.setUp
    register = FIX.NativeVehicleTests.register
    snap = FIX.NativeVehicleTests.snap
    breach = FIX.NativeVehicleTests.breach
    hit = FIX.NativeVehicleTests.hit

    def test_typeless_hit_applies_and_defensive_glass_refuses_atomically(self):
        row = self.register(template='personal', occupied=False)
        before_hp = row['hp']
        result = self.hit(8, kind='None', event='typeless-vehicle-hit')
        self.assertEqual(result['type_multiplier'], [1, 1])
        self.assertEqual(row['hp'], before_hp - 8)
        self.assertIn(TYPES.GLASS, TYPES.allowed_types(self.poly))
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'not Glass attacks'):
            self.hit(8, kind=TYPES.GLASS, event='defensive-glass-rejected')
        self.assertEqual(self.snap(), before)

"""Test illustrative spin geometry without Blender or third-party modules."""
import importlib.util
import math
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('rotation', Path(__file__).resolve().parents[1] / 'art/rotation.py')
rotation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rotation)


def conjugate(q):
    return (q[0], -q[1], -q[2], -q[3])


def difference(a, b):
    q = rotation.multiply(a, conjugate(b))
    return tuple(-v for v in q) if q[0] < 0 else q


class RotationTests(unittest.TestCase):
    def test_sixteen_tilted_spins_and_four_small_tumbles(self):
        settings = [rotation.profile(i) for i in range(1, 21)]
        self.assertEqual(sum(p['mode'] == 'tilted_spin' for p in settings), 16)
        self.assertEqual(sum(p['mode'] == 'gentle_tumble' for p in settings), 4)
        for p in settings:
            self.assertTrue(18 <= p['tilt_degrees'] <= 46.000001)
            self.assertIn(p['wobble_degrees'], [0, 10])
            self.assertAlmostEqual(sum(x*x for x in p['axis']), 1)
            self.assertAlmostEqual(sum(x*x for x in p['perpendicular']), 1)
            self.assertAlmostEqual(sum(a*b for a, b in zip(p['axis'], p['perpendicular'])), 0)

    def test_every_pose_is_normalized_and_preserves_the_approved_initial_pose(self):
        for number in range(1, 21):
            self.assertEqual(rotation.orientation(number, 0), (1, 0, 0, 0))
            for frame in range(241):
                pose = rotation.orientation(number, frame / 240)
                self.assertAlmostEqual(sum(x*x for x in pose), 1)

    def test_loops_close_with_continuous_motion(self):
        step = 1 / 240
        for number in range(1, 21):
            end = difference(rotation.orientation(number, 1), rotation.orientation(number, 0))
            self.assertAlmostEqual(end[0], 1)
            for v in end[1:]:
                self.assertAlmostEqual(v, 0)
            entering = difference(rotation.orientation(number, 1), rotation.orientation(number, 1-step))
            leaving = difference(rotation.orientation(number, step), rotation.orientation(number, 0))
            # Adjacent angular steps meet without a visible speed or direction jump.
            self.assertLess(math.dist(entering, leaving), 0.0001)

    def test_steady_variants_really_use_a_fixed_world_axis(self):
        for number in range(1, 21):
            p = rotation.profile(number)
            if p['mode'] != 'tilted_spin':
                continue
            for phase in [.13, .37, .61, .89]:
                pose = rotation.orientation(number, phase)
                length = math.sqrt(sum(v*v for v in pose[1:]))
                axis = tuple(v / length for v in pose[1:])
                self.assertAlmostEqual(abs(sum(a*b for a, b in zip(axis, p['axis']))), 1)

    def test_tumbling_is_bounded_and_changes_the_instantaneous_axis(self):
        for number in rotation.TUMBLING_VARIANTS:
            p = rotation.profile(number)
            for phase in [0, .125, .25, .5, .75]:
                base = rotation.axis_angle(p['axis'], math.tau * phase)
                wobble = difference(rotation.orientation(number, phase), base)
                angle = 2 * math.acos(min(1, max(-1, wobble[0])))
                self.assertLessEqual(math.degrees(angle), 10.000001)
            axes = []
            for phase in [0, .25, .5]:
                delta = difference(rotation.orientation(number, phase+.0001), rotation.orientation(number, phase))
                length = math.sqrt(sum(v*v for v in delta[1:]))
                axes.append(tuple(v / length for v in delta[1:]))
            self.assertGreater(math.dist(axes[0], axes[1]), .05)

    def test_invalid_variant_numbers_are_rejected(self):
        for number in [0, 21, -1]:
            with self.assertRaises(ValueError):
                rotation.profile(number)


if __name__ == '__main__':
    unittest.main()

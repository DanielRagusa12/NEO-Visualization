"""Illustrative rotation profiles, not measured asteroid spin or rigid-body physics.

Quaternions use Blender's (w, x, y, z) order. This module is dependency-free so
loop closure, axis stability, and bounded wobble can be tested without Blender.
"""
import math

TUMBLING_VARIANTS = frozenset({4, 8, 12, 19})


def profile(number):
    if number not in range(1, 21):
        raise ValueError('Variant number must be between 1 and 20')
    tilt = math.radians(18 + number * 11 % 29)
    azimuth = math.radians(number * 137.508 % 360)
    axis = (math.sin(tilt) * math.cos(azimuth), math.sin(tilt) * math.sin(azimuth), math.cos(tilt))
    perpendicular = (math.cos(tilt) * math.cos(azimuth), math.cos(tilt) * math.sin(azimuth), -math.sin(tilt))
    tumble = number in TUMBLING_VARIANTS
    return {
        'mode': 'gentle_tumble' if tumble else 'tilted_spin',
        'axis': axis,
        'perpendicular': perpendicular,
        'tilt_degrees': math.degrees(tilt),
        'wobble_degrees': 10 if tumble else 0,
    }


def axis_angle(axis, angle):
    sine = math.sin(angle / 2)
    return (math.cos(angle / 2), *(component * sine for component in axis))


def multiply(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return (w*v - x*i - y*j - z*k,
            w*i + x*v + y*k - z*j,
            w*j - x*k + y*v + z*i,
            w*k + x*j - y*i + z*v)


def orientation(number, phase):
    """One turn per loop, with a small periodic nutation on four variants.

    The nutation is an artistic approximation of tumbling, not a free-rigid-body
    simulation. Its amplitude and velocity both join continuously at the loop.
    """
    settings = profile(number)
    spin = axis_angle(settings['axis'], math.tau * phase)
    wobble = math.radians(settings['wobble_degrees']) * math.sin(math.tau * phase)
    return multiply(spin, axis_angle(settings['perpendicular'], wobble))

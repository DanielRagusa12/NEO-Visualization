"""Prepare 20 transparent rotation studios from the approved variation study.

Run in Blender with --disable-autoexec and --python-exit-code 1. The study must
already be open. Outputs default to OS temporary storage, never static/.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import tempfile

import bpy
from mathutils import Quaternion

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rotation import orientation, profile

COUNT = 20
FPS = 30
FRAMES = 240
RESOLUTION = 256


def linear_rotation(obj):
    obj.animation_data_clear()
    obj.keyframe_insert(data_path='rotation_euler', frame=1)
    obj.rotation_euler.z += math.tau
    obj.keyframe_insert(data_path='rotation_euler', frame=FRAMES + 1)
    linear_keyframes(obj)


def varied_rotation(obj, number):
    initial = obj.rotation_euler.to_quaternion()
    obj.animation_data_clear()
    obj.rotation_mode = 'QUATERNION'
    for frame in range(1, FRAMES + 2):
        phase = (frame - 1) / FRAMES
        obj.rotation_quaternion = Quaternion(orientation(number, phase)) @ initial
        obj.keyframe_insert(data_path='rotation_quaternion', frame=frame)
    linear_keyframes(obj)


def linear_keyframes(obj):
    for layer in obj.animation_data.action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = 'LINEAR'


def add_light(scene, name, position, energy, size, color):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy, data.size, data.color = energy, size, color
    data.shape = 'DISK'
    light = bpy.data.objects.new(name, data)
    scene.collection.objects.link(light)
    light.location = position
    light.rotation_euler = (-light.location).to_track_quat('-Z', 'Y').to_euler()


def prepare(output, engine, motion):
    study = bpy.data.scenes.get('20 asteroid variations - review')
    if study is None:
        raise RuntimeError('Open neo-variations-study.blend before running this script')
    study.frame_set(1)
    rocks = sorted((obj for obj in study.objects if obj.get('seed') is not None), key=lambda obj: obj.name)
    if len(rocks) != COUNT:
        raise RuntimeError('The approved study must contain exactly 20 variants')
    for number, source in enumerate(rocks, 1):
        name = f'NEO variant {number:02d}'
        if bpy.data.scenes.get(name):
            raise RuntimeError('Variation studios already exist; start from the study source')
        scene = bpy.data.scenes.new(name)
        scene.use_fake_user = True
        scene.world = study.world
        scene.render.engine = 'BLENDER_EEVEE' if engine == 'eevee' else 'CYCLES'
        scene.eevee.taa_render_samples = 64
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 12
        scene.cycles.use_denoising = True
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = 4
        scene.render.use_persistent_data = True
        scene.render.resolution_x = scene.render.resolution_y = RESOLUTION
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.image_settings.color_depth = '8'
        scene.render.film_transparent = True
        scene.render.dither_intensity = 0
        scene.view_settings.view_transform = study.view_settings.view_transform
        scene.frame_start, scene.frame_end, scene.render.fps = 1, FRAMES, FPS
        scene.render.fps_base = 1
        rock = source.copy()
        rock.name = f'Variant {number:02d} - {source["family"]}'
        scene.collection.objects.link(rock)
        rock.location = (0, 0, 0)
        if motion == 'varied':
            varied_rotation(rock, number)
        else:
            linear_rotation(rock)
        camera_data = bpy.data.cameras.new(name + ' camera')
        camera_data.type = 'ORTHO'
        camera_data.ortho_scale = 3.0
        camera = bpy.data.objects.new(name + ' camera', camera_data)
        scene.collection.objects.link(camera)
        camera.location = (0, -7, 0.035)
        camera.rotation_euler = (-camera.location).to_track_quat('-Z', 'Y').to_euler()
        scene.camera = camera
        add_light(scene, name + ' key', (-3.5, -3, 4.5), 550, 2.5, (1.0, 0.94, 0.85))
        add_light(scene, name + ' fill', (2.8, -2, 0.6), 75, 3.0, (0.84, 0.9, 1.0))
        add_light(scene, name + ' rim', (1, 2, 2.5), 230, 2.0, (1, 1, 1))
        # Every rotated vertex fits inside the orthographic frame with a margin.
        if max(vertex.co.length for vertex in rock.data.vertices) >= camera_data.ortho_scale * 0.48:
            raise RuntimeError('Rotation could clip against the image border: ' + name)
        scene['variant_id'] = f'variant-{number:02d}'
        scene['seed'] = source['seed']
        scene['family'] = source['family']
        scene['illustrative_only'] = True
        scene['motion_profile'] = motion
        if motion == 'varied':
            settings = profile(number)
            scene['spin_mode'] = settings['mode']
            scene['spin_axis'] = list(settings['axis'])
            scene['tilt_degrees'] = settings['tilt_degrees']
            scene['wobble_degrees'] = settings['wobble_degrees']
        scene.frame_set(1)
    if bpy.data.libraries or bpy.data.texts:
        raise RuntimeError('Studio must have no external libraries or embedded Python')
    filename = 'neo-varied-motion-studio.blend' if motion == 'varied' else 'neo-variations-studio.blend'
    source_path = output / filename
    bpy.ops.wm.save_as_mainfile(filepath=str(source_path))
    if motion == 'varied':
        profiles = {f'variant-{i:02d}': profile(i) for i in range(1, COUNT + 1)}
        (output / 'rotation-profiles.json').write_text(json.dumps(profiles, indent=2) + '\n')
    print('Saved editable studios:', source_path, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--only', nargs='+', choices=[f'{i:02d}' for i in range(1, COUNT + 1)])
    parser.add_argument('--engine', choices=['cycles', 'eevee'], default='cycles')
    parser.add_argument('--motion', choices=['axial', 'varied'], default='varied')
    parser.add_argument('--preview-frames', type=int, help='Render a short timing/quality sample, not a deliverable')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    if args.preview_frames is not None and not 1 <= args.preview_frames <= FRAMES:
        parser.error('--preview-frames must be between 1 and 240')
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='neo-variation-renders-'))
    output.mkdir(parents=True, exist_ok=True)
    if bpy.data.scenes.get('NEO variant 01') is None:
        prepare(output, args.engine, args.motion)
    for number in args.only or [f'{i:02d}' for i in range(1, COUNT + 1)]:
        scene = bpy.data.scenes.get('NEO variant ' + number)
        if scene is None or scene.render.fps != FPS or scene.frame_end != FRAMES:
            raise RuntimeError('Unexpected scene or loop timing: ' + number)
        if scene.get('motion_profile', 'axial') != args.motion:
            raise RuntimeError('Saved studio motion does not match --motion: ' + number)
        if scene.render.engine != ('BLENDER_EEVEE' if args.engine == 'eevee' else 'CYCLES'):
            raise RuntimeError('Saved studio engine does not match --engine: ' + number)
        if (scene.render.resolution_x, scene.render.resolution_y) != (RESOLUTION, RESOLUTION):
            raise RuntimeError('Unexpected render dimensions: ' + number)
        folder = output / 'neos' / ('variant-' + number)
        folder.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(folder / 'frame_')
        original_end = scene.frame_end
        if args.preview_frames:
            scene.frame_end = args.preview_frames
        print('Rendering', number, 'to', folder, flush=True)
        bpy.ops.render.render(animation=True, scene=scene.name)
        scene.frame_end = original_end
        scene.render.use_persistent_data = False
        print('Completed', number, flush=True)


if __name__ == '__main__':
    main()

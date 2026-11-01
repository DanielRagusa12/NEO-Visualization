"""Generate an editable 20-shape study and contact sheets, not production assets.

Run with Blender --background --factory-startup --disable-autoexec --threads 4
--python-exit-code 1 --python variations.py -- --output /tmp/neo-study-EXAMPLE.
Only Blender's bundled Python modules are used. No network or downloaded assets.
"""
import argparse
import math
from pathlib import Path
import random
import sys
import tempfile

import bpy
from mathutils import Vector, noise

# Dimensions are artistic proportions, not measurements of NASA objects.
# The long axis stays modest: none of these are thin wedges or needles.
VARIANTS = [
    ('Rounded',       (1.00, 0.93, 0.98), 0.13, 22, 0, 0.00),
    ('Blocky',        (1.12, 0.87, 0.98), 0.12,  9, 5, 0.00),
    ('Oblong',        (0.80, 0.91, 1.24), 0.15, 17, 1, 0.00),
    ('Flattened',     (1.16, 0.85, 0.81), 0.12, 24, 2, 0.00),
    ('Lobed',         (1.02, 0.90, 1.09), 0.16, 13, 1, 0.15),
    ('Broad',         (1.17, 0.92, 0.91), 0.18, 12, 2, 0.00),
    ('Faceted',       (0.96, 1.01, 1.10), 0.10, 10, 6, 0.00),
    ('Pitted',        (1.02, 0.92, 1.04), 0.14, 32, 0, 0.00),
    ('Compact',       (0.95, 1.02, 0.96), 0.21, 17, 2, 0.00),
    ('Elongated',     (0.91, 0.90, 1.26), 0.16, 14, 3, 0.00),
    ('Lumpy',         (1.06, 0.91, 1.04), 0.23, 16, 0, 0.09),
    ('Broad crater',  (1.12, 0.96, 0.92), 0.14, 11, 2, 0.00),
    ('Rugged',        (0.97, 0.85, 1.12), 0.22, 26, 3, 0.00),
    ('Blunt',         (1.03, 1.04, 0.94), 0.13, 14, 5, 0.00),
    ('Uneven lobes',  (0.97, 0.90, 1.14), 0.18, 16, 1, 0.18),
    ('Low profile',   (1.19, 0.98, 0.78), 0.18, 21, 3, 0.00),
    ('Broken face',   (1.09, 0.92, 1.04), 0.17, 13, 6, 0.00),
    ('Weathered',     (0.95, 0.98, 1.09), 0.12, 30, 1, 0.00),
    ('Asymmetric',    (1.11, 0.88, 1.06), 0.24, 14, 2, 0.10),
    ('Chunky',        (1.06, 1.01, 1.03), 0.20, 19, 4, 0.00),
]


def unit_vector(rng):
    z = rng.uniform(-1, 1)
    angle = rng.uniform(0, math.tau)
    radius = math.sqrt(1 - z * z)
    return Vector((radius * math.cos(angle), radius * math.sin(angle), z))


def make_material(index, rng):
    material = bpy.data.materials.new(f'Rock {index:02d} - procedural')
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    links = material.node_tree.links
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (700, 0)
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (430, 0)
    shader.inputs['Roughness'].default_value = 0.93
    shader.inputs['Specular IOR Level'].default_value = 0.22
    links.new(shader.outputs['BSDF'], output.inputs['Surface'])
    coordinates = nodes.new('ShaderNodeTexCoord')
    coordinates.location = (-850, 0)
    mapping = nodes.new('ShaderNodeVectorMath')
    mapping.operation = 'ADD'
    mapping.location = (-660, 0)
    mapping.inputs[1].default_value = tuple(rng.uniform(1, 30) for _ in range(3))
    links.new(coordinates.outputs['Generated'], mapping.inputs[0])
    texture = nodes.new('ShaderNodeTexNoise')
    texture.location = (-450, 150)
    texture.inputs['Scale'].default_value = 5.5
    texture.inputs['Detail'].default_value = 5.0
    texture.inputs['Roughness'].default_value = 0.78
    links.new(mapping.outputs['Vector'], texture.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.location = (-120, 170)
    # Restrained charcoal, neutral grey and warm stone. Never metallic.
    tones = [(0.24, 0.225, 0.20), (0.185, 0.185, 0.18),
             (0.27, 0.25, 0.22), (0.21, 0.20, 0.19)]
    tone = tones[(index - 1) % len(tones)]
    ramp.color_ramp.elements[0].position = 0.12
    ramp.color_ramp.elements[0].color = (*(x * 0.38 for x in tone), 1)
    ramp.color_ramp.elements[1].position = 0.88
    ramp.color_ramp.elements[1].color = (*(x * 1.55 for x in tone), 1)
    links.new(texture.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], shader.inputs['Base Color'])
    grain = nodes.new('ShaderNodeTexNoise')
    grain.location = (-450, -180)
    grain.inputs['Scale'].default_value = 42
    grain.inputs['Detail'].default_value = 3.5
    grain.inputs['Roughness'].default_value = 0.8
    links.new(mapping.outputs['Vector'], grain.inputs['Vector'])
    fine_bump = nodes.new('ShaderNodeBump')
    fine_bump.location = (-120, -150)
    fine_bump.inputs['Strength'].default_value = 0.48
    fine_bump.inputs['Distance'].default_value = 0.045
    links.new(grain.outputs['Fac'], fine_bump.inputs['Height'])
    broad_bump = nodes.new('ShaderNodeBump')
    broad_bump.location = (170, -110)
    broad_bump.inputs['Strength'].default_value = 0.32
    broad_bump.inputs['Distance'].default_value = 0.085
    links.new(texture.outputs['Fac'], broad_bump.inputs['Height'])
    links.new(fine_bump.outputs['Normal'], broad_bump.inputs['Normal'])
    links.new(broad_bump.outputs['Normal'], shader.inputs['Normal'])
    return material


def make_rock(index, config, collection):
    family, axes, roughness, crater_count, cut_count, waist = config
    seed = 42000 + index * 137
    rng = random.Random(seed)
    offset = Vector(tuple(rng.uniform(-50, 50) for _ in range(3)))
    craters = []
    for _ in range(crater_count):
        center = unit_vector(rng)
        radius = rng.uniform(0.11, 0.34)
        depth = rng.uniform(0.05, 0.12)
        craters.append((center, radius, depth))
    if family == 'Broad crater':
        craters.append((Vector((0.12, -0.98, 0.14)).normalized(), 0.55, 0.23))
    cuts = [(unit_vector(rng), rng.uniform(0.76, 0.93)) for _ in range(cut_count)]
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=1)
    rock = bpy.context.object
    rock.name = f'{index:02d} - {family}'
    for owner in list(rock.users_collection):
        owner.objects.unlink(rock)
    collection.objects.link(rock)
    for vertex in rock.data.vertices:
        direction = vertex.co.normalized()
        broad = noise.noise(direction * 1.65 + offset, noise_basis='PERLIN_ORIGINAL')
        medium = noise.noise(direction * 5.4 + offset, noise_basis='PERLIN_ORIGINAL')
        fine = noise.noise(direction * 18 + offset, noise_basis='PERLIN_ORIGINAL')
        radius = 1 + roughness * broad + 0.075 * medium + 0.026 * fine
        if waist:
            radius -= waist * math.exp(-((direction.z - 0.12) / 0.36) ** 2)
        for center, size, depth in craters:
            # Chord distance is stable at crater centres and cheaper than acos.
            distance = (direction - center).length / size
            if distance < 1.3:
                bowl = -depth * max(0, 1 - distance * distance) ** 2
                rim = depth * 0.38 * math.exp(-((distance - 0.94) / 0.13) ** 2)
                radius += bowl + rim
        position = direction * radius
        for normal, plane in cuts:
            excess = position.dot(normal) - plane
            if excess > 0:
                # Rounded fracture boundaries rather than razor-thin wedge tips.
                position -= normal * (excess * 0.92)
        vertex.co = Vector((position.x * axes[0], position.y * axes[1], position.z * axes[2]))
    # Centre the mesh and give every tile the same maximum illustrated dimension.
    minimum = Vector(tuple(min(v.co[axis] for v in rock.data.vertices) for axis in range(3)))
    maximum = Vector(tuple(max(v.co[axis] for v in rock.data.vertices) for axis in range(3)))
    center = (minimum + maximum) * 0.5
    factor = 2.25 / max(maximum - minimum)
    for vertex in rock.data.vertices:
        vertex.co = (vertex.co - center) * factor
    rock.data.update()
    for polygon in rock.data.polygons:
        polygon.use_smooth = True
    rock.data.materials.append(make_material(index, rng))
    rock['seed'] = seed
    rock['family'] = family
    rock['illustrative_only'] = True
    rock['generator'] = 'neowebsite/art/variations.py'
    rock['axes'] = list(axes)
    rock['macro_roughness'] = roughness
    rock['crater_count'] = crater_count
    rock['fracture_count'] = cut_count
    rock.rotation_euler = (rng.uniform(-0.38, 0.38), rng.uniform(-0.3, 0.3), rng.uniform(-0.4, 0.4))
    rock.keyframe_insert(data_path='rotation_euler', frame=1)
    rock.rotation_euler.z += math.tau
    rock.keyframe_insert(data_path='rotation_euler', frame=121)
    action = rock.animation_data.action
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                for curve in channelbag.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = 'LINEAR'
    return rock


def text_material():
    material = bpy.data.materials.new('Contact sheet labels')
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (0.68, 0.68, 0.68, 1)
    material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
    return material


def add_label(text, position, collection, material, size=0.19):
    curve = bpy.data.curves.new(text, 'FONT')
    curve.body = text
    curve.align_x = 'CENTER'
    curve.size = size
    curve.extrude = 0
    obj = bpy.data.objects.new(text, curve)
    collection.objects.link(obj)
    obj.location = position
    obj.rotation_euler.x = math.pi / 2
    obj.data.materials.append(material)


def area_light(collection, name, location, target, energy, size, color):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = energy
    data.shape = 'DISK'
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def build_study():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = '20 asteroid variations - review'
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 4
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1400
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    world = bpy.data.worlds.new('Black space')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.009, 0.009, 0.009, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.4
    models = bpy.data.collections.new('Editable seeded asteroid meshes')
    scene.collection.children.link(models)
    studio = bpy.data.collections.new('Camera, labels and studio lights')
    scene.collection.children.link(studio)
    label = text_material()
    for index, config in enumerate(VARIANTS, 1):
        column, row = (index - 1) % 5, (index - 1) // 5
        x, z = (column - 2) * 3.3, 4.9 - row * 3.2
        rock = make_rock(index, config, models)
        rock.location = (x, 0, z)
        add_label(f'{index:02d}  {config[0]}', (x, -0.1, z - 1.42), studio, label)
        # Each tile has the same small light rig. Light linking prevents spill.
        receivers = bpy.data.collections.new(f'{index:02d} light receivers')
        receivers.objects.link(rock)
        for name, delta, energy, size, color in [
            ('key', (-3.5, -3, 4.5), 550, 2.5, (1.0, 0.94, 0.85)),
            ('fill', (2.8, -2, 0.6), 75, 3.0, (0.84, 0.9, 1.0)),
            ('rim', (1.0, 2, 2.5), 230, 2.0, (1.0, 1.0, 1.0)),
        ]:
            area_light(studio, f'{index:02d} {name}', (x + delta[0], delta[1], z + delta[2]),
                       (x, 0, z), energy, size, color)
            light = studio.objects[f'{index:02d} {name}']
            light.light_linking.receiver_collection = receivers
    add_label('ASTEROID SHAPE STUDY / 20 SEEDED VARIATIONS', (0, -0.1, 7.08), studio, label, 0.24)
    add_label('Illustrative geometry, not measured NASA shapes. Same scale and lighting for every tile.',
              (0, -0.1, -6.75), studio, label, 0.15)
    camera_data = bpy.data.cameras.new('Contact sheet camera')
    camera = bpy.data.objects.new('Contact sheet camera', camera_data)
    studio.objects.link(camera)
    camera.location = (0, -30, 0)
    camera.rotation_euler = (Vector((0, 0, 0.15)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = 17.5
    scene.camera = camera
    scene.frame_start, scene.frame_end = 1, 120
    scene.render.fps = 30
    scene.frame_set(1)
    scene['purpose'] = 'Review shape variety before choosing and exporting production assets.'
    scene['preview_frames'] = '1 = initial angle, 31 = quarter turn, 61 = half turn'
    scene['generator'] = 'neowebsite/art/variations.py'
    # Open on the camera, without embedding or enabling Python in the blend file.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
    return scene


def validate(scene):
    rocks = [obj for obj in scene.objects if obj.get('seed') is not None]
    if len(rocks) != 20 or len({obj['seed'] for obj in rocks}) != 20:
        raise RuntimeError('Expected twenty distinct seeded meshes')
    fingerprints = {tuple(round(v, 5) for vertex in obj.data.vertices for v in vertex.co) for obj in rocks}
    if len(fingerprints) != 20:
        raise RuntimeError('Duplicate geometry in study')
    if bpy.data.libraries or bpy.data.texts:
        raise RuntimeError('Study must not contain external libraries or embedded Python')
    print('Validated 20 distinct editable meshes; no external libraries or embedded scripts.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--views', nargs='+', type=int, choices=[1, 31, 61], default=[1, 31])
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='neo-variations-'))
    output.mkdir(parents=True, exist_ok=True)
    print('Study output:', output, flush=True)
    scene = build_study()
    validate(scene)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'neo-variations-study.blend'))
    for frame in args.views:
        scene.frame_set(frame)
        scene.render.filepath = str(output / f'contact-sheet-{frame:03d}.png')
        bpy.ops.render.render(write_still=True)
        print('Rendered', scene.render.filepath, flush=True)
    scene.frame_set(1)


if __name__ == '__main__':
    main()

"""Render the editable asset studio. Run through Blender with --python-exit-code 1."""
import argparse
from pathlib import Path
import sys
import tempfile

import bpy

REFERENCES = {
    'eiffel-tower': ('Eiffel reference', 440, 'height'),
    'burj-khalifa': ('Burj reference', 440, 'height'),
    'everest': ('Everest reference', 480, 'width'),
    'human': ('Human reference', 440, 'height'),
    'statue-of-liberty': ('Liberty reference', 440, 'height'),
}
LOOPS = {'cratered': 360, 'angular': 420, 'elongated': 480, 'wedge': 540}


def export_reference(source, destination, target, axis):
    image = bpy.data.images.load(str(source), check_existing=False)
    width, height = image.size
    pixels = list(image.pixels[:])
    xmin, ymin, xmax, ymax = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if pixels[(y * width + x) * 4 + 3] > 0.015:
                xmin, xmax = min(xmin, x), max(xmax, x)
                ymin, ymax = min(ymin, y), max(ymax, y)
    if xmax < 0:
        raise RuntimeError('Reference render is empty: ' + str(source))
    xmin, ymin = max(0, xmin - 2), max(0, ymin - 2)
    xmax, ymax = min(width - 1, xmax + 2), min(height - 1, ymax + 2)
    cropped = []
    for y in range(ymin, ymax + 1):
        cropped.extend(pixels[(y * width + xmin) * 4:(y * width + xmax + 1) * 4])
    w, h = xmax - xmin + 1, ymax - ymin + 1
    output = bpy.data.images.new('Reference export', width=w, height=h, alpha=True)
    output.pixels.foreach_set(cropped)
    factor = target / (w if axis == 'width' else h)
    output.scale(round(w * factor), round(h * factor))
    output.filepath_raw = str(destination)
    output.file_format = 'PNG'
    output.save()
    print(destination.name, tuple(output.size), flush=True)
    bpy.data.images.remove(image)
    bpy.data.images.remove(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--only', nargs='+', choices=[*REFERENCES, *LOOPS], default=[*REFERENCES, *LOOPS])
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args = parser.parse_args(arguments)
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='neo-renders-'))
    output.mkdir(parents=True, exist_ok=True)
    print('Render output:', output, flush=True)
    for name in args.only:
        scene_name = REFERENCES[name][0] if name in REFERENCES else 'NEO 30fps ' + name
        scene = bpy.data.scenes.get(scene_name)
        if scene is None:
            raise RuntimeError('Missing asset scene: ' + scene_name)
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = 4
        scene.cycles.device = 'CPU'
        if name in REFERENCES:
            folder = output / 'references'
            folder.mkdir(exist_ok=True)
            source = folder / (name + '-master.png')
            scene.render.filepath = str(source)
            scene.frame_set(1)
            bpy.ops.render.render(write_still=True, scene=scene_name)
            _, target, axis = REFERENCES[name]
            export_reference(source, folder / (name + '.png'), target, axis)
        else:
            if scene.frame_start != 1 or scene.frame_end != LOOPS[name] or scene.render.fps != 30:
                raise RuntimeError('Unexpected loop timing: ' + name)
            if (scene.render.resolution_x, scene.render.resolution_y) != (256, 256):
                raise RuntimeError('Unexpected loop resolution: ' + name)
            folder = output / 'neos' / name
            folder.mkdir(parents=True, exist_ok=True)
            scene.render.filepath = str(folder / 'frame_')
            bpy.ops.render.render(animation=True, scene=scene_name)


if __name__ == '__main__':
    main()

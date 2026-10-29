"""Encode local render frames using installed FFmpeg tools; never downloads tooling."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

REFERENCES = ['eiffel-tower', 'burj-khalifa', 'everest', 'human', 'statue-of-liberty']
LOOPS = {'cratered': 360, 'angular': 420, 'elongated': 480, 'wedge': 540}


def run(command, binary=False):
    return subprocess.run(command, check=True, timeout=300, stdout=subprocess.PIPE,
                          text=not binary).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renders', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--only', nargs='+', choices=[*REFERENCES, *LOOPS], default=[*REFERENCES, *LOOPS])
    args = parser.parse_args()
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='neo-encoded-'))
    info = {}
    if any(name in LOOPS for name in args.only) and not all(shutil.which(t) for t in ['ffmpeg', 'ffprobe']):
        parser.error('Install and review FFmpeg with libvpx-vp9 and libwebp support before encoding.')
    for name in args.only:
        if name in REFERENCES:
            destination = output / 'references' / (name + '.png')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.renders / 'references' / destination.name, destination)
            info['references/' + destination.name] = {'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
            continue
        count = LOOPS[name]
        frames = args.renders / 'neos' / name
        for index in range(1, count + 1):
            with (frames / f'frame_{index:04d}.png').open('rb') as stream:
                header = stream.read(24)
            if header[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', header[16:24]) != (256, 256):
                raise RuntimeError('Unexpected input frame in ' + name)
        folder = output / 'neos'
        folder.mkdir(parents=True, exist_ok=True)
        video = folder / (name + '-spin-30fps.webm')
        poster = folder / (name + '-poster.webp')
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-framerate', '30',
             '-start_number', '1', '-i', str(frames / 'frame_%04d.png'), '-frames:v', str(count),
             '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-auto-alt-ref', '0',
             '-b:v', '0', '-crf', '32', '-deadline', 'good', '-cpu-used', '4',
             '-row-mt', '1', '-threads', '4', '-g', '120', str(video)])
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(frames / 'frame_0001.png'),
             '-frames:v', '1', '-c:v', 'libwebp', '-quality', '85', '-pix_fmt', 'yuva420p', str(poster)])
        probe = json.loads(run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                               '-show_entries', 'stream=r_frame_rate,nb_read_frames:format=duration',
                               '-of', 'json', str(video)]))
        stream = probe['streams'][0]
        duration = float(probe['format']['duration'])
        if stream['r_frame_rate'] != '30/1' or int(stream['nb_read_frames']) != count or abs(duration - count / 30) > 0.05:
            raise RuntimeError('Unexpected encoded timing in ' + name)
        # The native VP9 decoder can discard alpha; force libvpx to validate it.
        alpha = run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-c:v', 'libvpx-vp9',
                     '-i', str(video), '-vf', 'alphaextract', '-frames:v', '1',
                     '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], binary=True)
        if len(alpha) != 256 * 256 or alpha[0] != 0 or max(alpha) < 250:
            raise RuntimeError('Missing transparent video alpha in ' + name)
        for path in [video, poster]:
            info['neos/' + path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                        'bytes': path.stat().st_size}
        info['neos/' + video.name].update(fps=30, frames=count, duration_seconds=duration, alpha_verified=True)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'asset-info.json').write_text(json.dumps(info, indent=2) + '\n')
    print('Encoded assets:', output)


if __name__ == '__main__':
    main()

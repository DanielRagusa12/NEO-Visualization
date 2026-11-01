"""Asset-export guards using synthetic headers, without Blender or FFmpeg execution."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

ART = Path(__file__).resolve().parents[1] / 'art'
SPEC = importlib.util.spec_from_file_location('asset_encoder', ART / 'encode.py')
encoder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(encoder)


class ArtExportTests(unittest.TestCase):
    def test_variants_have_complete_numbering_and_eight_second_timing(self):
        self.assertEqual(list(encoder.VARIATIONS), [f'variant-{i:02d}' for i in range(1, 21)])
        self.assertEqual(set(encoder.VARIATIONS.values()), {240})

    def invoke(self, folder, *extra):
        argv = ['encode.py', '--renders', str(folder), '--output', str(folder / 'encoded'),
                '--only', 'variant-01', *extra]
        with mock.patch('sys.argv', argv), mock.patch.object(encoder.shutil, 'which', return_value='/synthetic/ffmpeg'):
            encoder.main()

    def test_short_preview_is_rejected_before_encoding(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(encoder, 'run') as run:
            folder = Path(root)
            frames = folder / 'neos' / 'variant-01'
            frames.mkdir(parents=True)
            header = b'\x89PNG\r\n\x1a\n' + b'\x00' * 8 + struct.pack('>II', 256, 256)
            for index in range(1, 31):
                (frames / f'frame_{index:04d}.png').write_bytes(header)
            with self.assertRaises(FileNotFoundError):
                self.invoke(folder, '--crf', '42')
            run.assert_not_called()

    def test_incorrect_dimensions_are_rejected_before_encoding(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(encoder, 'run') as run:
            folder = Path(root)
            frames = folder / 'neos' / 'variant-01'
            frames.mkdir(parents=True)
            (frames / 'frame_0001.png').write_bytes(
                b'\x89PNG\r\n\x1a\n' + b'\x00' * 8 + struct.pack('>II', 128, 256))
            with self.assertRaisesRegex(RuntimeError, 'Unexpected input frame'):
                self.invoke(folder)
            run.assert_not_called()

    def test_quality_outside_reviewable_range_is_rejected(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(encoder, 'run') as run, \
             mock.patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                self.invoke(Path(root), '--crf', '64')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

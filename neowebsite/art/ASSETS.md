# Model assets

`neo-asset-studio.blend` contains the five reference studios and the four retained v1 asteroid studios. It opens on the Liberty camera. `neo-variations-studio.blend` preserves the v2 single-axis animations. `neo-varied-motion-studio.blend` contains the active 20 tilted-spin/tumbling studios plus the approved contact-sheet scene. Choose a scene from Blender's scene selector and use its configured camera.

Authored with Blender 5.2.3 LTS and FFmpeg 9.0.2. No MCP addon is required to open or render these files. They contain no embedded Python, external texture dependencies, or MCP settings. If working in a sandbox, copy the source into its asset workspace rather than exposing your home directory or cloud credentials.

The reference assets are Eiffel Tower, Burj Khalifa, a stylized Everest illustration, a neutral 1.7 m mannequin, and the Statue of Liberty. Liberty's 93 m comparison height includes its pedestal. Its seven-ray crown, torch, tablet, robe, and pedestal are editable geometry. All new geometry and procedural materials were authored for this project, without downloaded models or external generation services.

These are illustrations, not measured asteroid shapes, anatomical scans, architectural surveys, or geographic terrain reconstructions. Everest uses summit elevation above sea level rather than local mountain relief. Rotation axes and periods are artistic choices.

## Browser assets

Only `../static/` is deployed. The active browser assets are:

- Five unchanged reference PNGs in `../static/assets/models/v1/references/`, cropped to their visible bounds and exported without stretching.
- Twenty WebP posters in `../static/assets/models/v3/neos/`.
- Twenty silent, transparent VP9 WebM loops in that v3 directory. Each is 256 × 256, 30 fps, and eight seconds long. Variant numbers match the approved contact sheet.

`manifest-v3.json` records the current asteroid files, hashes, timing, rotation profiles, and editable source. `manifest.json` and `manifest-v2.json` record retained v1/v2 assets. Keep old versions for cached clients during the transition. NEO identifiers select v3 variants through a deterministic FNV-1a hash, so sorting, changing references, and reloading do not change an object's shape. Twenty variants reduce repetition but do not guarantee a different shape for every object.

The player checks actual alpha support and uses a poster if playback or transparency is unsupported. It also respects reduced-motion preferences, suspends offscreen playback, and uses static rendering below 32 pixels. References do not rotate. The active v3 asteroid catalogue plus the five references totals 3.81 MiB. Tests cap it at 4 MiB total and each v3 video at 256 KiB. Only visible, sufficiently large asteroids load video. Editable sources and retained v1/v2 loops are outside the active catalogue budget.

Do not copy `.blend` files, source scripts, master renders, or intermediate frames into `static/`. Blender backups and the optional local `renders/` directory are ignored.

## Local preview and checks

Run from the repository root:

```bash
python3 neowebsite/dev_server.py
node --test neowebsite/tests/*.test.mjs
python3 -m unittest discover -s neowebsite/tests -p 'test_*.py'
```

The preview binds only to `127.0.0.1:8001` and serves the real site with explicitly synthetic test data. It does not fetch production data or contact AWS. Production continues to fetch only same-origin `/data/latest.json`.

## Regenerate retained v1 assets

Use installed, reviewed Blender and FFmpeg binaries. FFmpeg must include `libvpx-vp9`, `libwebp`, and `ffprobe`. These scripts do not install packages or download assets. Keep credentials out of the authoring environment and leave automatic Blender script execution disabled.

For one NEO loop:

```bash
blender --background --factory-startup --disable-autoexec --threads 4 \
  --python-exit-code 1 neowebsite/art/neo-asset-studio.blend \
  --python neowebsite/art/render.py -- --only cratered
```

The renderer prints its temporary output directory. Supply that directory to the encoder:

```bash
python3 neowebsite/art/encode.py --renders /tmp/neo-renders-EXAMPLE --only cratered
```

Use `--only eiffel-tower`, `burj-khalifa`, `everest`, `human`, or `statue-of-liberty` for references. Omit `--only` to regenerate the full set. Both scripts default to OS temporary output directories and leave the shipped assets unchanged. Rendering the full set is CPU-intensive; the renderer is bounded to four threads.

The encoder checks frame counts, 30 fps timing, loop duration, and decoded transparency. Review its output and `asset-info.json` before replacing browser files. A changed reference crop can require updating `REFERENCE_ASSETS` aspect ratios in `static/main.js`.

For changed browser assets, use a new version directory and update `ASSET_ROOT`, the manifest, and tests. Keep older versioned files during a cache transition. Asset objects cache for a day; entrypoints cache for five minutes. Update the HTML entrypoint query revisions with script or stylesheet changes. Those revisions bypass browser caches, not CloudFront's managed cache policy, which ignores query strings; account for its TTL or invalidate changed entrypoints during rollout.

## Variation study

`neo-variations-study.blend` is the approved shape batch used to prepare the current asteroid studios. `variations.py` regenerates its 20 seeded asteroid meshes. It does not change the approved studio or any files in `static/`. The batch varies proportions, large-scale irregularity, crater placement, fracture faces, and mild lobes. Materials are procedural, with no downloaded textures. Shapes and rotation are illustrative, not NASA reconstructions.

```bash
blender --background --factory-startup --disable-autoexec --threads 4 \
  --python-exit-code 1 --python neowebsite/art/variations.py -- \
  --output /tmp/neo-variation-review
```

The output contains `neo-variations-study.blend` and numbered contact sheets at the initial angle and a quarter turn. Add `--views 1 31 61` to include a half-turn sheet. Every tile has the same illustrated maximum dimension and light rig. In Blender, select a numbered mesh to inspect its seed and shape parameters in Custom Properties. All geometry, materials, lights, and rotation keyframes remain editable. Regenerate geometry by editing the corresponding entry in `VARIANTS` and rerunning the script, rather than changing the descriptive custom properties alone.

Review a changed batch before exporting replacement posters or videos. Review renders stay in temporary storage, not `static/`.

## Export the 20 active variants

Prepare individual studios from the approved study and render the complete loops:

```bash
blender --background --factory-startup --disable-autoexec --threads 4 \
  --python-exit-code 1 neowebsite/art/neo-variations-study.blend \
  --python neowebsite/art/render_variations.py -- \
  --output /tmp/neo-motion-renders --engine eevee --motion varied

python3 neowebsite/art/encode.py --renders /tmp/neo-motion-renders \
  --output /tmp/neo-motion-encoded --only variant-{01..20} --crf 40
```

EEVEE uses 64 render samples and requires an available graphics context. The initial export used the installed AMD GPU in a network-isolated filesystem sandbox. `--engine cycles` prepares CPU studios instead, with four threads and denoising, but that is a separate render configuration to review. No packages, textures, or models are downloaded.

The renderer saves `neo-varied-motion-studio.blend` before rendering. Sixteen variants rotate about fixed, tilted world axes. Variants 04, 08, 12, and 19 add a periodic 10-degree nutation as a gentle tumble. This is an artistic approximation, not a free-rigid-body solver or measured NASA motion. `rotation.py` defines the testable quaternion profiles; frame 1 preserves each approved pose. Quaternions are baked at every frame, with continuous loop orientation and angular steps. Change the profiles and regenerate rather than editing descriptive Scene custom properties alone.

All 20 studios have persistent scene users, transparent output, a fixed camera margin across the full rotation, and a 240-frame loop with its closing keyframe at 241. Use `--motion axial` to prepare or rerender the original v2 Euler animations instead. `--only 01 02` selects studios. `--preview-frames 30` makes a short timing/quality sample, which the encoder rejects as an incomplete deliverable.

The encoder verifies every frame's dimensions, the exact frame count, 30 fps timing, duration, and decoded alpha. Its `asset-info.json` supplies the hashes and sizes for `manifest-v3.json`; the renderer's `rotation-profiles.json` supplies the motion metadata. After reviewing an export, copy only the posters and loops into a new static version directory, retain the editable studio in `art/`, and update the source hashes and tests. The reference PNGs do not need re-exporting.

## Deployment

The Terraform website fileset uploads the new assets and includes their exact paths in the CloudFront allowlist. `website.tf` includes WebP and WebM MIME mappings. A Terraform apply is required; copying files outside Terraform will not update the path guard.

Review the deployment plan separately. Publish the new asset paths and allowlist before switching cached entrypoints, and retain old assets until cached clients have expired. Do not expose the private buckets or introduce browser-triggered Lambda or database requests.

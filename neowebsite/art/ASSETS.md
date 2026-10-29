# Model assets

`neo-asset-studio.blend` is the editable source for the approved models. It contains ten scenes: five reference studios, one NEO source-model scene, and four 30 fps rotation studios. Choose a scene from Blender's scene selector and use its configured camera. The file opens on the Liberty camera.

Authored with Blender 5.2.3 LTS and FFmpeg 9.0.2. No MCP addon is required to open or render the file. It contains no embedded Python, external texture dependencies, or MCP settings. If working in a sandbox, copy this file into its asset workspace rather than exposing your home directory or cloud credentials.

The reference assets are Eiffel Tower, Burj Khalifa, a stylized Everest illustration, a neutral 1.7 m mannequin, and the Statue of Liberty. Liberty's 93 m comparison height includes its pedestal. Its seven-ray crown, torch, tablet, robe, and pedestal are editable geometry. All new geometry and procedural materials were authored for this project, without downloaded models or external generation services.

These are illustrations, not measured asteroid shapes, anatomical scans, architectural surveys, or geographic terrain reconstructions. Everest uses summit elevation above sea level rather than local mountain relief. Rotation axes and periods are artistic choices.

## Browser assets

Only `../static/` is deployed. Browser files live in `../static/assets/models/v1/`:

- Five reference PNGs, cropped to their visible bounds and exported without stretching.
- Four static WebP posters.
- Four silent VP9 WebM loops with transparency, rendered at 256 × 256 and 30 fps. Their durations are 12, 14, 16, and 18 seconds.

`manifest.json` records the shipped files' hashes and render metadata. The player checks actual alpha support and uses a poster if playback or transparency is unsupported. It also preserves pause controls, reduced-motion preferences, offscreen suspension, and static rendering below 32 pixels. References do not rotate. Tests cap the version's browser model assets at 4 MiB total and each video at 1 MiB; the editable source is outside that delivery budget.

Do not copy `.blend` files, source scripts, master renders, or intermediate frames into `static/`. Blender backups and the optional local `renders/` directory are ignored.

## Local preview and checks

Run from the repository root:

```bash
python3 neowebsite/dev_server.py
node --test neowebsite/tests/*.test.mjs
python3 -m unittest discover -s neowebsite/tests -p 'test_*.py'
```

The preview binds only to `127.0.0.1:8001` and serves the real site with explicitly synthetic test data. It does not fetch production data or contact AWS. Production continues to fetch only same-origin `/data/latest.json`.

## Regenerate assets

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

## Deployment

The Terraform website fileset uploads the new assets and includes their exact paths in the CloudFront allowlist. `website.tf` includes WebP and WebM MIME mappings. A Terraform apply is required; copying files outside Terraform will not update the path guard.

Review the deployment plan separately. Publish the new asset paths and allowlist before switching cached entrypoints, and retain old assets until cached clients have expired. Do not expose the private buckets or introduce browser-triggered Lambda or database requests.

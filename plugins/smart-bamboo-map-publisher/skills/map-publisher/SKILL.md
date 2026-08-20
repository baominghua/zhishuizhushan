---
name: smart-bamboo-map-publisher
description: Package, scan, classify, upload, or troubleshoot Smart Bamboo map assets including GeoTIFF orthophotos, DSM/DTM, LAS/LAZ point clouds, and DJI PNTS/B3DM 3D Tiles. Use when preparing map material publication or maintaining the downloadable Windows map publishing assistant.
---

# 智慧竹山地图发布助手

Prefer the packaged graphical assistant in `scripts/SmartBambooMapPublisher.ps1`. Keep command-line publishing in `scripts/publish-material.ps1` so the GUI and automation share one implementation.

## Classification

- `result.tif`, `orthophoto.tif`, or visible-light TIFF: orthophoto.
- `dsm.tif`: DSM surface model.
- `dtm.tif` or DEM-named TIFF: DTM terrain model.
- A directory with root `tileset.json` and `.b3dm`: DJI textured model.
- A directory with root `tileset.json` and `.pnts`: DJI point-cloud tiles.
- A directory containing `.las` or `.laz`: raw point-cloud task.

Do not merge B3DM and PNTS. Publish them to separate dataset directories and return a separate platform path for each.

## Safety

- Require an explicit publish action before uploading.
- Never store passwords. Use the configured private key and Windows OpenSSH.
- Validate remote roots as absolute Linux paths without `..`.
- Upload into a temporary path, verify content/hash, then atomically replace the published path.
- Move an existing same-name target into `.releases`; do not delete it directly.
- Output the `/app/data/remote-sensing/inbox/...` path for platform registration.

## Distribution

The platform download endpoint packages the launcher, GUI, CLI, batch runner, sample config, and Chinese help from this plugin. Update source files here, then run plugin validation and the download endpoint test before release.

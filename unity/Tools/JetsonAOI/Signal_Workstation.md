# Signal AOI workstation

## Approved design

The source is the approved `aoi-signal-workstation.html` conversation preview. Its machine surface is 1024 x 983.46875 logical pixels. `export-signal-layout.cjs` captures the static artwork and button states at 2x resolution and exports element rectangles, font settings and padding into `Resources/AoiSignal/layout.json`.

No photographed MOSFET is baked into the production background. Main/crop images and inspection fields are supplied by the existing AOI feed. `reference-ng.png` is a design reference only.

## Rendering

- The popup uses a native Unity ScreenSpaceOverlay canvas, so scene exposure and tone mapping do not change its palette.
- The offscreen monitor camera also disables exposure/postprocessing for inspection screenshots.
- PNG artwork is imported as sRGB, without compression or mipmaps, without NPOT scaling, with a 4096 texture limit.
- Static backgrounds/buttons use the exported artwork. Dynamic fields use the exported element rectangles and system font families.
- Long values are shortened in the small fixed fields; full inspection IDs remain available through the history view.
- Product/region display crops only affect display, not the input JPEG, model results, original image or source detection coordinates.

The shared artwork, colors and element coordinates are exact design inputs. Dynamic content, display resolution, font rasterization and the physical 3D monitor can still differ from a browser screenshot; this is not a claim of universal pixel identity.

## Controls

- Left **검사**: inspection workspace.
- Left **기록**: existing daily/source filters, history paging, ID details and daily normal rate.
- Left **연결**: session-only token entry, paste/apply, and camera settings/live view.
- **제품 / 전체 이미지 / 선택 영역**: product crop, original whole image and selected defect crop.
- **불량 검출 / 제품 인식**: detection versus part-recognition details.
- **다시 촬영**: existing Jetson inspection request; requires a valid session token and a fresh live frame in camera mode.
- **NG 분류 실행**: existing guarded manual sorting; unknown/expired/duplicate results remain blocked.
- **Escape**: dismiss the settings modal or close the monitor popup.

No database link or new authentication method was introduced.

## Backup and tests

`Tools/aoi-signal-backup.txt` points to the pre-change dashboard/feed/editor scripts and corrected scene, with SHA-256 hashes in `manifest.json`.

`AoiSignalUpgrade.status` records uncompressed artwork import. `AoiLightUpgrade.status` and `.result` record saved-scene/runtime checks. They use an isolated temporary history store, DEMO inputs and saved-JPEG replay; they do not constitute a fresh live Jetson-camera inspection. The workstation checks additionally verify that the screen overlay is independent of scene lighting and that the approved artwork is loaded.

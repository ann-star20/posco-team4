# AOI operator dashboard

Applied to `Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity`.

## Layout

- Dark operator console, 1200 x 970 logical canvas.
- Larger camera/result image, 692 x 428, with full image, defect zoom, live camera, and product zoom controls.
- Result, detection list, and two paged defect crops on the right.
- Daily completed/OK/NG/normal-rate statistics and recent inspection history below.
- Existing history filtering, direct Jetson requests, session-only token, camera settings, and manual sorting retained.
- Database state is explicitly shown as not connected.

Product zoom uses the union of the received valid part and defect bounding boxes with padding. It changes display only; the original image and transmitted inspection frame are unchanged. Full-image view remains available. Live video remains separate from the last inspection result.

## Backup

`Tools/aoi-operator-console-backup.txt` identifies the pre-change code and scene backup. Its `manifest.json` contains SHA-256 hashes. A separate editor scene snapshot is also created before each rebuild.

To restore the former dashboard, close Play, restore the backed-up dashboard/feed scripts and corrected scene to their original paths, then refresh Unity. Keep asset metadata GUIDs unchanged.

## Verification

`AoiLightUpgrade.result` and `.status` record the Unity runtime checks. These use an isolated temporary history store, DEMO packets, and saved JPEG replay. They exercise waiting/OK/NG, sorting destinations and duplicate prevention, one/two/three defect paging and pointer clicks, full/product/defect/live views, history/day/source separation, and daily normal-rate statistics. They do not establish a new authenticated live Jetson inspection or database integration.

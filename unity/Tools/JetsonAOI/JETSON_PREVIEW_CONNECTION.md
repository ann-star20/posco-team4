# Unity ↔ Jetson frame inspection

Default Jetson: `192.168.213.167`.

## Camera source: IP Webcam

Start the IP Webcam server on the smartphone. Configure Jetson AOI to read
`http://<phone IP>:<port>/video`; preserve authentication settings if used.
The phone and Jetson must be reachable over the network. Update the source URL when the phone IP changes.
Unity receives preview frames from Jetson 8500 and sends inspection requests to Jetson 8400;
it does not read the smartphone MJPEG URL directly. The Windows laptop sender is optional and is not required for this setup.
See [IP Webcam setup](../../docs/SETUP.md#ip-웹캠-연결).

## Operator connection

1. Open the AOI monitor and select **연결 → Jetson 영상 연결 · 8500**.
2. Address: `ws://192.168.213.167:8500/camera/preview` (entering the IP alone also works).
3. Camera ID: `aoi-camera-1`. Enter the separately supplied `CAMERA_PREVIEW_TOKEN` in the masked video token field, then connect.
4. In **연결**, enter `AOI_UNITY_TOKEN` in the masked inspection token field and apply it.
5. Select **실시간 영상**, position the part, then select **검사**.

Only the endpoint and camera ID are saved. Tokens stay in the current Play session; they are not written into scenes, logs or preferences.

## Wire behavior

- Preview sends `camera.preview.subscribe` and requires a subscribed acknowledgement, then repeated frame metadata/JPEG binary pairs.
- Each displayed image retains its corresponding camera ID and numeric frame ID. Pending newer frames are not used until displayed.
- The inspection request goes to port 8400 on the same Jetson host and contains new request/job/run UUIDs plus the selected camera/frame IDs. It sends no JPEG upload, `input_image` or fixture selector.
- The displayed JPEG is copied locally for the existing 3-second scan presentation. The preview connection may continue receiving newer frames without changing the inspection selection.
- Results retain existing request/job/run/lot/unit matching, JPEG hash/length/dimension validation and contradictory-verdict rejection. Frame inspection requires `result_origin=prod`. If the server echoes a camera/frame pair, it must match.
- The sample documentation lists only important completed fields. The full response must retain the identity/schema/timestamp/image fields required by the established AOI result contract.
- After a verified result, the product view appears and the Unity equipment routes eligible OK/NG results. Review, low confidence, expired results and duplicate delivery remain blocked.
- `persistence_status=queued` is displayed as queued; it is not a database-completion acknowledgement.

The former phone MJPEG/8401 adapter is no longer selected by the monitor's current-frame inspection flow. Its helper scripts are retained for rollback.
The central Gateway 8000 event/approval/correction interface is not changed by this video/AOI migration; its exact message contract was not supplied.

## Checks

- `test-preview-protocol.ps1`: addresses, metadata/JPEG integrity, frame ordering, request shape/UUIDs, correlated prod-only results.
- `test-unity-protocol.ps1`: existing AOI result validation regression checks.
- Unity `AoiPreviewChecks`: displayed-versus-pending frame binding, independent local freeze copy, stale/disconnected frame rejection.
- Unity `AoiLightUpgrade`: dashboard, scan, local history and equipment-routing regression checks using an isolated test store.

These tests do not establish real model accuracy or prove an authenticated connection to a live camera.

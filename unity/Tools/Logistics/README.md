# HOLD LOT isolation in the Unity simulation

Both ELLIP-01 and IMP-01 unload finished, mechanically safe FOUPs through OHT to the six-slot stocker. A quality HOLD or an unfinished Gateway full cycle is isolated; no carrier is sent to the downstream production tool while its acceptance is unresolved.

- Existing request/run/inspection IDs and each Gateway stream remain active during Play.
- The stocker reserves the returned slot and blocks production dispatch of that carrier. A next inspection allocates a separate free slot and a new `SIM-LOT-*` / wafer / carrier identity. This is explicitly a new simulated input using the same registered TCAD reference recipe, not a real factory arrival or a fallback for an unknown real LOT.
- The prior FOUP remains visible in its slot. Raw inspection and Gateway request objects stay frozen. Responses update records by exact inspection ID.
- A parked carrier waiting for its original inspection/prediction results is labeled `RESULT WAIT`, not an NG verdict. When both original equipment/electrical checks and the surrogate prediction are OK, with no diagnosis/correction route, it is automatically dispatched from its stocker slot to the I/O outbound handoff. The occupied/reservation flags and parked visual are cleared only after dispatch succeeds. This is the simulation's outbound boundary, not a modeled trip to another factory or a real hardware command.
- An original NG, a prediction NG, missing results, failed requests, diagnosis `no_action`, or successful TCAD validation never qualifies for normal automatic export. NG remains latched for review. In particular, TCAD completion never releases an NG HOLD, modifies a recipe, or automatically reprocesses a wafer.
- Normal dispatch can free a parked carrier's slot while a different input carrier remains reserved. Carrier references and that active reservation are restored after dispatch. A normally exported active carrier is replenished only as a new explicit simulation LOT at the next inspection.
- The stocker has finite capacity. Occupied/held slots are never overwritten. Full stocker or eight unfinished Gateway jobs prevents new simulated input, while current subscriptions remain alive.
- Stocker panel lists held LOTs, slots, and Gateway status; Result opens that inspection's analysis.
- `Tools/Logistics/Hold/session-*.json` is a local simulation audit, not proof of Gateway DB persistence. Inventory and streams live for the Play session. The file is not automatically restored after stopping Play; server-side jobs remain independent.

Offline checks: `HoldLotIsolationCheck.once` (policy), `NormalLotExportCheck.once` (real scene geometry, safe return, OHT/stocker animation, pending and already-normal film/ion dispatch, full stocker, active and non-active carrier export, NG and late TCAD protection). They do not send Gateway requests. The flow check uses the existing offline CSV fixture and temporary histories; it exits Play after finishing.

## Manual X button for simulation slots

Each parked LOT row has an X button. When equipment, OHT and stocker are idle, it removes only that simulated FOUP visual and its occupied/reserved slot flags. The row leaves the active stocker list; the inspection remains in local history and Gateway jobs and streams remain unchanged. The audit marks `manualRemoved: true`, keeps the original NG flag, and records `시연 수동 반출`, never normal approval. Both the active reserved FOUP and a parked cloned FOUP are supported. Repeated clicks on an old row cannot remove a replacement LOT. Busy transfers disable the button.

Offline fixture: `ManualLotRemoveCheck.once` -> `ManualLotRemoveCheck.result`. Covers full prior film/ion recovery and normal export plus manual NG removal, slot reuse, original record/request preservation, busy rejection and stale-row rejection. No Gateway request is sent by the fixture.

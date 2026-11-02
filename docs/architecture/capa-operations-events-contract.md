# CAPA 운영 이벤트 API — Unity 연동 계약 (v1, 작업 1+2A)

- 기준일: 2026-10-24
- 상태: Gateway 쪽 구현·테스트·실제 호출 확인 완료(작업 1, 2A). 작업 2B(시간 구간 저장)/2C(조회 화면)는 아직 미구현.
- 대상: Unity 팀 — CAPA 대시보드용 운영 이벤트를 Gateway로 보내는 쪽 구현 시 참고.

## 1. 엔드포인트

```
POST /api/v1/operations/events
GET  /api/v1/factory/overview?factory_session_id=<uuid>
```

- 인증: 기존 Unity 연동과 동일한 헤더 `x-unity-token: <UNITY_API_TOKEN>` (다른 Unity API와 토큰 공유).
- `POST`는 성공 시 `202`, body `{"event_id": "...", "sequence": 123}`.
- `GET /api/v1/factory/overview`는 세션이 없으면 `404`.

이 API는 ML 추론(`surrogate-jobs`/`diagnosis-jobs`)이나 TCAD 승인 API와 **완전히 독립**이다 — 운영 이벤트가 ML 작업을 만들지 않고, `run_id`를 쓰지 않는다(아래 §4).

## 2. 공통 이벤트 필드

```json
{
  "schema_version": 1,
  "event_id": "<uuid, 매 이벤트마다 새로 생성>",
  "event_type": "session.started | session.ended | equipment.registered | lot.registered | equipment.state_changed | lot.activity_changed | lot.disposition_changed",
  "source": "unity.factory",
  "severity": "info",
  "factory_session_id": "<uuid, Play 시작 시 1회 생성해서 세션 끝까지 재사용>",
  "payload": { "...": "이벤트 타입별 필드, §3 참고" },
  "occurred_at": "2026-10-24T14:08:41.236641Z"
}
```

`event_id`는 **매번 새로 생성**하되, 네트워크 오류로 응답을 못 받은 경우 **같은 event_id로 그대로 재전송**한다 (§5 재시도 규칙).

## 3. 이벤트 타입별 payload — 실제 테스트로 확인된 예시

### 3.1 `session.started` / `session.ended`
Play 시작/종료 시 딱 한 번씩. payload는 빈 객체로 충분하다.
```json
{"event_type": "session.started", "payload": {}}
```

### 3.2 `equipment.registered`
세션 시작 후, 등록할 설비마다 한 번씩(최대 6건: 산화로/산화막검사기/이온주입기/AOI/OHT/스토커).
```json
{
  "event_type": "equipment.registered",
  "payload": {
    "equipment_id": "OX-01",
    "equipment_kind": "oxidation"
  }
}
```
`equipment_kind` ∈ `oxidation | film_inspection | ion_implant | aoi | oht | stocker`. 스토커는 `slot_count`도 같이 보낸다:
```json
{"equipment_id": "STOCKER-01", "equipment_kind": "stocker", "slot_count": 6}
```

### 3.3 `lot.registered`
```json
{
  "event_type": "lot.registered",
  "payload": {
    "lot_id": "LOT-001",
    "lot_kind": "wafer_route",
    "representative_wafer_id": "WAFER-001"
  }
}
```
`lot_kind="wafer_route"`면 `representative_wafer_id` 필수(`product_id` 금지). `lot_kind="aoi_product"`면 `product_id` 필수(`representative_wafer_id` 금지).

### 3.4 `equipment.state_changed` / `lot.activity_changed` / `lot.disposition_changed` — 작업 2A, **가장 중요한 규칙**
설비나 LOT의 상태가 바뀔 때마다 보낸다. **일반 이벤트와 다르게 `state_version`/`prev_event_id`가 필수다.**

```json
{
  "event_type": "equipment.state_changed",
  "payload": {
    "equipment_id": "OX-01",
    "state": "running",
    "state_version": 1,
    "prev_event_id": null
  }
}
```
다음 상태 전이는 `state_version`을 1 증가시키고 `prev_event_id`에 **직전에 성공한 이벤트의 `event_id`**를 넣는다:
```json
{
  "event_type": "equipment.state_changed",
  "payload": {
    "equipment_id": "OX-01",
    "state": "idle",
    "state_version": 2,
    "prev_event_id": "<방금 전 요청에서 받은 event_id>"
  }
}
```

- `state` ∈ `idle | running | blocked | paused | down`
- `lot.activity_changed`의 `activity_status` ∈ `waiting | processing | transferring`
- `lot.disposition_changed`의 `disposition_status` ∈ `result_wait | quality_hold | completed | removed`
- **설비 1대, LOT 1개의 activity, LOT 1개의 disposition은 각각 독립적인 버전 계열이다** — 즉 `OX-01`의 `state_version`과 `LOT-001`의 `activity_status` `state_version`은 서로 무관하게 1부터 따로 올라간다. 섞어서 세지 않는다.

## 4. `run_id`를 안 쓰는 이유

이 API는 ML 작업(`run_id`)과 무관한 "공장 운영 시연 기록"이라서, Gateway 내부에서 저장되는 `events.run_id`는 항상 `NULL`이다. 세션 식별은 전부 `factory_session_id`로 한다. Unity 쪽에서 신경 쓸 건 없음 — 그냥 매 요청에 `factory_session_id`만 정확히 넣으면 된다.

## 5. 재시도 규칙 — Unity가 반드시 구현해야 하는 부분

### 5.1 일반 재시도 (멱등)
`session.*`/`equipment.registered`/`lot.registered`는 같은 `event_id`로 재전송하면 그대로 같은 응답(`202`)을 돌려준다 — 서버가 중복 처리하지 않는다. 응답을 못 받았으면 안전하게 같은 event_id로 다시 보내면 된다.

단, **다른 event_id로 같은 자원을 다시 등록하려 하면 `409`**를 돌려준다 (예: `OX-01`을 이미 등록했는데 새 event_id로 또 `equipment.registered`를 보냄). 이 경우 Unity는 재등록하면 안 된다 — 등록은 세션당 1회뿐이다.

### 5.2 상태 이벤트(`*_changed`) 재시도 — **영속 FIFO 필수**
이게 가장 중요하다. 설비/LOT별로 Unity는 **보낸 순서대로 하나씩, 이전 요청이 확정(202 또는 409 확인)되기 전까지 다음 상태를 보내면 안 된다.**

- 네트워크 끊김으로 ACK를 못 받았으면: 같은 이벤트를 다시 보낸다. 서버가 이미 받았으면 `202`(같은 결과), 아직이면 정상 처리 후 `202`.
- 서버가 `409`를 주면 응답 본문에 `expected_state_version`/`last_event_id`가 들어있다:
  ```json
  {"detail": {"message": "...", "expected_state_version": 2, "last_event_id": "..."}}
  ```
  이건 "이 상태 전이는 적용되지 않았다"는 뜻이다. Unity는 **로컬에 보관 중인 이벤트 큐에서 `expected_state_version`에 해당하는 이벤트부터 순서대로 다시 보낸다.** 임의로 버전을 건너뛰거나 지금 상태를 다시 추정해서 보내면 안 된다 — 로컬 큐에 그 이벤트가 없으면(복구 불가) 그 구간은 "불완전 계측"으로 남기고, 다음 정상적인 상태부터 새로 이어간다(자동 재정렬은 v1 범위 밖).
- 설비 A와 LOT B의 전송은 서로 독립적이다 — A가 막혀도 B는 계속 보낼 수 있다(§3.4의 버전 계열 분리와 같은 이유).

## 6. 실제 동작 확인 (2026-10-24, 라이브 Gateway 테스트)

- `session.started` → `equipment.registered`(산화로, 스토커+슬롯6) → `lot.registered`(wafer_route) → `GET /api/v1/factory/overview` 순서로 실제 호출, 응답 값 정확히 일치 확인.
- 같은 설비를 다른 event_id로 재등록 시도 → `409 equipment already registered by another event` 확인.
- `state_version` 1→3(2 건너뜀) 거부 → 2 적용 → 3 성공, 동시에 같은 `state_version`을 주장하는 두 이벤트 중 하나만 승인되고 나머지 `409`, 동일 이벤트 재전송 멱등성 — 전부 자동 테스트로 확인됨.

## 7. 작업 2B 완료 — 상태 구간이 이제 서버에 쌓인다

`equipment.state_changed`/`lot.activity_changed`/`lot.disposition_changed`가 **버전 검증을 통과할 때마다**(재전송 멱등인 경우는 제외) 서버가 자동으로:
1. 그 설비/LOT(activity 또는 disposition)의 기존 "열린 구간"을 `occurred_at` 시각에 닫고,
2. 새 상태로 "열린 구간"을 새로 연다.

Unity는 이 저장을 위해 **추가로 할 일이 없다** — §3.4의 `state_version`/`prev_event_id` 규칙만 지키면 구간은 서버가 알아서 계산한다. `occurred_at`을 정확히 보내는 게 중요해졌다(구간 시작/종료 시각의 근거가 되므로).

## 8. 아직 없는 것 (다음 단계)

- `GET /api/v1/factory/overview`/`capacity`에서 구간 데이터를 조회·집계해서 보여주는 것 — 작업 2C/4, 아직 없음. 지금은 DB에 구간이 쌓이기만 하고, 조회 API는 아직 §1의 `overview`(세션/설비/LOT 등록 정보만)에서 더 확장되지 않았다.

Unity 쪽은 지금 §3.4/§5.2의 버전·FIFO 규칙만 먼저 구현해두면, 2C가 붙을 때 Unity 쪽 변경 없이 바로 가동률/대기시간 화면이 붙는다.

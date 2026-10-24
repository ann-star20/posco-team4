# fake 서버2(8402) 시험 케이스 명세

Gateway가 TCAD 서비스 연동(승인 전 재검증 포함)을 계산 시간 없이 시험할 때 쓰는 서버.
주소·토큰·엔드포인트는 기존 TCAD 서비스와 동일하고, 아래 4개 공정값만 **즉시** 알고 있는 결과를 돌려준다.
그 외 값은 기존 fake(8401)와 같은 고정 canned 값으로 응답한다 (계산 안 함, 즉시 응답).

- 주소: `http://192.168.212.13:8402`
- 인증: `X-Fab-Token: <토큰값>` (운영자에게 별도 전달받을 것 — 이 문서/git에는 실제 값을 적지 않는다)
- 엔드포인트: `POST /api/v1/tcad/verify`, `GET /api/v1/tcad/jobs/{request_id}`, `POST /api/v1/tcad/jobs/{request_id}/cancel`, `GET /health/ready`
- 매칭 기준: 요청의 `process_parameters`(도즈/에피/산화막)가 아래 표의 값과 **비율 기준 0.1% 이내**로 같으면 해당 케이스로 응답. 안 맞으면 케이스 3(모름)으로 처리.

---

## 케이스 1: 불량 — 두 후보 다 BV 미달 (regection 유도)

| candidate | body_dose | epi_doping | oxide_thickness |
|---|---|---|---|
| 1-A | 7753340198236.813 | 2.210564350884519e+16 | 0.06392919205021827 |
| 1-B | 7537337500000.002 | 2.2100000000000016e+16 | 0.06402000000000002 |

**request (1-A)**
```json
POST /api/v1/tcad/verify
{
  "request_id": "case1-a",
  "process_parameters": {"body_dose": 7753340198236.813, "epi_doping": 2.210564350884519e16, "oxide_thickness": 0.06392919205021827}
}
```

**response (조회, 완료 후)**
```json
{
  "request_id": "case1-a", "status": "succeeded",
  "result_payload": {"vth": 2.354434589800445, "gm": 4.51, "id_on": 5.23, "bv": 36.76071514072834},
  "metadata": {"units": {"vth": "V", "gm": "uS/um", "id_on": "uA/um", "bv": "V"}, "warnings": []}
}
```
→ vth 통과(1.7~2.6V), **bv 미달(40V 미만)** → `spec_verdict.overall: "out_of_spec"`. 1-B도 같은 패턴(vth 2.301, bv 36.76). **둘 다 불량이라 프로포절 전체 반려(`rejected`) 되는지 확인하는 케이스.**

---

## 케이스 2: 정상 — 두 후보 중 하나 이상 OK (승인 유도)

| candidate | body_dose | epi_doping | oxide_thickness |
|---|---|---|---|
| 2-A | 9621876529144.201 | 1.2759703185067598e+16 | 0.054263109097874435 |
| 2-B | 10962875000000.004 | 1.2325000000000006e+16 | 0.04972500000000002 |

**request (2-A)**
```json
POST /api/v1/tcad/verify
{
  "request_id": "case2-a",
  "process_parameters": {"body_dose": 9621876529144.201, "epi_doping": 1.2759703185067598e16, "oxide_thickness": 0.054263109097874435}
}
```

**response (조회, 완료 후)**
```json
{
  "request_id": "case2-a", "status": "succeeded",
  "result_payload": {"vth": 2.4610425391227695, "gm": 4.537, "id_on": 4.575, "bv": 48.03779360510845},
  "metadata": {"units": {"vth": "V", "gm": "uS/um", "id_on": "uA/um", "bv": "V"}, "warnings": []}
}
```
→ vth·bv **둘 다 통과** → `spec_verdict.overall: "in_spec"`. 2-B도 같은 패턴(vth 2.461, bv 48.30). **하나(또는 둘)라도 OK면 프로포절이 승인 가능(`approved`) 상태로 가는지 확인하는 케이스.** (한쪽만 쓰고 싶으면 2-A만, 둘 다 섞어서 "2개 중 1개만 OK" 시험도 가능 — 둘 다 OK 조합이라 이 케이스는 "최소 1개 이상 OK"를 항상 만족한다.)

---

## 케이스 3: 모름 — 등록 안 된 임의 공정값 (기존 fake 폴백)

케이스 1·2에 없는 어떤 값을 보내도 기존 fake(8401)와 동일한 **고정 canned 값**을 즉시 돌려준다 (계산 흐름 자체를 시험할 때 사용).

**request**
```json
POST /api/v1/tcad/verify
{
  "request_id": "case3-anything",
  "process_parameters": {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}
}
```

**response**
```json
{
  "request_id": "case3-anything", "status": "succeeded",
  "result_payload": {"vth": 2.258302, "gm": 4.46, "id_on": 5.15, "bv": 41.11701}
}
```
→ vth·bv 둘 다 통과 (고정값이라 항상 동일). **TCAD 연동 배선 자체(접수→폴링→succeeded)만 확인할 때 쓴다.**

---

## 요약

| 케이스 | 목적 | 기대 분기 |
|---|---|---|
| 1 (불량 2개) | 반려 흐름 시험 | 전체 반려 |
| 2 (정상 포함) | 승인 흐름 시험 | 승인 가능 (최소 1개 `in_spec`) |
| 3 (모름) | 배선/흐름 시험 | 항상 `in_spec` (고정값) |

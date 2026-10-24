"""fake 서버2: 8401(fake)과 같은 API지만, 아래 KNOWN 두 후보(공정값)는 이미 real로 계산된 실제값을
계산 과정 없이 즉시 돌려준다. 그 외 요청은 기존 fake_calc(고정 canned 값)로 처리한다.
  python fake서버2.py --port 8402
"""
import argparse
import os

import 계산 as calc
import 서비스 as svc

KNOWN = [
    {  # b53860a7-f41f-51dd-b23f-611ac638706b (2026-10-24 17:24 real 완료)
        "process_parameters": {"body_dose": 7753340198236.813, "epi_doping": 2.210564350884519e+16, "oxide_thickness": 0.06392919205021827},
        "vth": 2.354434589800445, "gm_us_um": 4.510000000000016, "id_on_ua_um": 5.2299999999999995, "bv": 36.76071514072834,
        "i_leak": 4.742e-16, "seconds_iv": 686.4, "seconds_bv": 1849.2,
    },
    {  # 49ba6c2c-779d-50ad-a7e9-38b9765ec031 (2026-10-24 17:24 real 완료) - 불량(bv 미달)
        "process_parameters": {"body_dose": 7537337500000.002, "epi_doping": 2.2100000000000016e+16, "oxide_thickness": 0.06402000000000002},
        "vth": 2.3009846827133478, "gm_us_um": 4.569999999999996, "id_on_ua_um": 5.354, "bv": 36.76050673101629,
        "i_leak": 4.767e-16, "seconds_iv": 687.2, "seconds_bv": 1868.3,
    },
    {  # 03808647-f843-5282-ad3e-6c891e76431c (2026-10-23 21:xx real 완료) - 정상(OK, 규격 안)
        "process_parameters": {"body_dose": 9621876529144.201, "epi_doping": 1.2759703185067598e+16, "oxide_thickness": 0.054263109097874435},
        "vth": 2.4610425391227695, "gm_us_um": 4.537000000000016, "id_on_ua_um": 4.575, "bv": 48.03779360510845,
        "i_leak": 5.457e-16, "seconds_iv": 335.1, "seconds_bv": 1497.7,
    },
    {  # c06e6114-9bb2-5ebd-96b3-00fbb7503b90 (2026-10-23 21:xx real 완료) - 정상(OK, 규격 안)
        "process_parameters": {"body_dose": 10962875000000.004, "epi_doping": 1.2325000000000006e+16, "oxide_thickness": 0.04972500000000002},
        "vth": 2.461351122405761, "gm_us_um": 4.7220000000000155, "id_on_ua_um": 4.651999999999999, "bv": 48.29706526263708,
        "i_leak": 5.47e-16, "seconds_iv": 343.8, "seconds_bv": 1512.3,
    },
]
REL_TOL = 1e-3
for _k in KNOWN:
    _k["ratios"] = calc.ratios(_k["process_parameters"])

_orig_fake = calc.fake_calc


def _find_known(row):
    r = {"dose": row["바디도즈비율"], "epi": row["에피도핑비율"], "tox": row["산화막비율"]}
    for k in KNOWN:
        kr = k["ratios"]
        if all(abs(r[a] - kr[a]) <= REL_TOL * max(abs(kr[a]), 1e-30) for a in ("dose", "epi", "tox")):
            return k
    return None


def patched_calc(row, report_stage, is_cancelled):
    known = _find_known(row)
    if known is None:
        return _orig_fake(row, report_stage, is_cancelled)
    report_stage("iv", 0)
    r = {"status": "ok", "vth": known["vth"], "gm": known["gm_us_um"] / 1e6, "id4v": known["id_on_ua_um"] / 1e6,
         "i_leak": known["i_leak"], "seconds": known["seconds_iv"], "sweep": float(row["스윕(V)"]),
         "시도": [{"스윕": float(row["스윕(V)"]), "격자": 1.0}]}
    if row["BV계산"] == "Y":
        report_stage("bv", known["seconds_iv"])
        r["bvt_levels"] = {"1e-09": known["bv"]}
        r["bvt_seconds"] = known["seconds_bv"]
    return r


calc.get_calc_fn = lambda: patched_calc

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8402)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--token", default=os.environ.get("TCAD_SERVICE_TOKEN"))
    a = ap.parse_args()
    svc.setup_logging()
    service = svc.Service(token=a.token)
    server = svc.make_server(a.port, service, a.host)
    svc.LOG.info("TCAD fake서버2 시작: http://%s:%s  (알고있는 후보 %d개는 즉시 응답, 나머지는 기존 fake)", a.host, a.port, len(KNOWN))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        svc.LOG.info("종료")

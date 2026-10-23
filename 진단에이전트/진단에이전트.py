"""진단 에이전트: 이상 로트의 측정값에서 어떤 공정 노브가 벗어났는지 베이지안으로 추정하고, 정직하게 "구분 불가"를 말하고,
다음에 무엇을 재면 좋은지 권고하고, 제어 가능한 노브(도즈·산화막)로 보정안을 내고, 마지막에 고정밀 모드로 확인한다.

흐름
  1) 후보 격자: 노브 (도즈, 에피, 산화막) 비율 후보 약 5만 개를 in_domain 안에서 만들고 기본 모드(2단 GP)로 한 번에 예측한다.
  2) 사후분포: 측정값과의 가우시안 가능도 (분산 = 측정 잡음²/웨이퍼 수 + 서로게이트 σ²(보정됨)). 사전분포는 격자 위 균등.
  3) 판정: 노브 8가지 조합(정상/도즈/에피/…/3개 모두; 비율이 기준에서 delta 이상 벗어난 노브 집합) 중 확률이 tau 이상이면 판정, 아니면 구분 불가.
  4) 다음 측정 권고: 후보 행동(BV 측정, 웨이퍼 2배·4배)마다 사후분포에서 가상 측정을 뽑아 판정 확률이 얼마나 오르는지 계산해 가장 도움이 되는 행동을 고른다.
  5) 보정안: 에피는 제어 불가. 도즈·산화막 배율을 사후분포 전체에서 기준값 특성으로 되돌리는 쪽으로 고른다 (서로게이트 기준).
  6) 고정밀 확인: 사후 상위 후보와 보정 후 상태를 고정밀 모드(GP+TabPFN)로 다시 예측해 판정이 바뀌는지 본다 (없으면 건너뜀).
  7) TCAD 확인 요청: 보정 후 노브 값을 TCAD 로 한 번 돌릴 작업으로 내보낸다 (오케스트레이터가 실행).

모든 값은 TCAD 합성 데이터로 학습한 서로게이트 기준이다. 측정 잡음은 가정값(노이즈가정.py 와 같은 값)이다.
  python 진단에이전트.py       # 자체 점검과 시연
"""
import re
import importlib.util
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FINAL = HERE.parent / "최종ML"
NOISE = dict(vth=0.05, gm=0.05, id4v=0.05, bv=0.3)                 # 가정 측정 잡음: Vth·BV 는 절대(V), gm·Id 는 상대. 노이즈가정.py 와 같은 값
CAT_NAMES = ["정상", "도즈", "에피", "도즈+에피", "산화막", "도즈+산화막", "에피+산화막", "도즈+에피+산화막"]       # 비트: 도즈=1, 에피=2, 산화막=4
KNOB = ("도즈", "에피", "산화막")
SPEC = dict(vth=(1.7, 2.6), bv_min=40.0)


def load_class(name, folder=FINAL):
    f = next(p for p in Path(folder).glob("*.py") if re.search(rf"^class {name}\b", p.read_text(encoding="utf-8"), re.M))
    s = importlib.util.spec_from_file_location("m_" + name, f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return getattr(m, name)


def _obs(meas):
    o = {}
    if meas.get("vth") is not None:
        o[0] = (float(meas["vth"]), NOISE["vth"])
    if meas.get("gm") is not None:
        o[1] = (float(np.log(meas["gm"])), NOISE["gm"])
    if meas.get("id4v") is not None:
        o[2] = (float(np.log(meas["id4v"])), NOISE["id4v"])
    if meas.get("bv") is not None:
        o[3] = (float(meas["bv"]), NOISE["bv"])
    if not o:
        raise ValueError("측정값이 하나도 없다")
    return o


def _loglik(P, S, obs, n):
    ll = np.zeros(len(P))
    for j, (y, sn) in obs.items():
        var = sn ** 2 / n + S[:, j] ** 2
        ll += -0.5 * ((y - P[:, j]) ** 2 / var + np.log(var))
    return ll


def _softmax(ll):
    w = np.exp(ll - ll.max())
    return w / w.sum()


def _wquantile(v, w, qs):
    o = np.argsort(v)
    c = np.cumsum(w[o]) - 0.5 * w[o]
    return np.interp(qs, c / c[-1], v[o])


class DiagnosisAgent:
    def __init__(self, surrogate, pipeline=None, step=0.025, delta=0.05, tau=0.70, seed=0):
        """surrogate: raw_calibrated(X)·domain(X)·info 를 가진 Surrogate. pipeline: 고정밀 확인에 쓸 TwoStagePipeline(없으면 건너뜀)."""
        self.sur, self.pipe, self.delta, self.tau = surrogate, pipeline, delta, tau
        self.rng = np.random.default_rng(seed)
        d, e, t = np.arange(0.70, 1.70001, step), np.arange(0.30, 1.70001, step), np.arange(0.50, 1.40001, step)
        G = np.stack(np.meshgrid(d, e, t, indexing="ij"), -1).reshape(-1, 3)
        self.G = G[self.sur.domain(G)]
        self.P, self.S = self.sur.raw_calibrated(self.G)            # 격자 전체 예측 (평균 [Vth, ln gm, ln Id, BV], 보정된 σ)
        self.mask = ((np.abs(self.G - 1) > delta) @ np.array([1, 2, 4])).astype(int)
        b = surrogate.info["기준값"]
        self.base = np.array([b["vth"], np.log(b["gm"]), np.log(b["id4v"]), b["bv"]])

    # ------------------------------------------------------------ 2~3) 사후분포와 판정
    def _cat(self, w, mask):
        return np.bincount(mask, weights=w, minlength=8)

    def _summary(self, w, G, mask):
        cat = self._cat(w, mask)
        order = np.argsort(-cat)
        top = int(order[0])
        knobs = []
        for k in range(3):
            v = G[:, k]
            q = _wquantile(v, w, [0.05, 0.5, 0.95])
            knobs.append(dict(노브=KNOB[k], 평균=float(w @ v), 중앙값=float(q[1]), 구간90=(float(q[0]), float(q[2])), 벗어날확률=float(w[np.abs(v - 1) > self.delta].sum())))
        return dict(범주확률={CAT_NAMES[i]: float(cat[i]) for i in range(8)}, 최다=CAT_NAMES[top], 최다확률=float(cat[top]), 판정됨=bool(cat[top] >= self.tau),
                    후보=[(CAT_NAMES[i], float(cat[i])) for i in order if cat[i] >= 0.10], 노브=knobs, MAP=G[int(np.argmax(w))].tolist())

    def _fine_grid(self, w, step=0.005, mass=0.999, pad=0.03, max_points=150_000):
        """거친 격자의 사후분포가 모인 상자 안을 step 간격으로 다시 촘촘히 만든다 (사후분포가 좁을 때 격자 간격 때문에 구간이 틀어지는 것을 막는다)."""
        o = np.argsort(-w)
        k = int(np.searchsorted(np.cumsum(w[o]), mass)) + 1
        pts = self.G[o[:k]]
        lo, hi = np.maximum(pts.min(0) - pad, [0.7, 0.3, 0.5]), np.minimum(pts.max(0) + pad, [1.7, 1.7, 1.4])
        axes = [np.arange(lo[a], hi[a] + 1e-9, step) for a in range(3)]
        if np.prod([len(a) for a in axes]) > max_points:
            return None
        F = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
        F = F[self.sur.domain(F)]
        return F if len(F) else None

    def diagnose(self, meas, n_wafers=1, prior_sigma=None, prior_laplace=None, fine=True):
        """meas: dict(vth(V), gm(A/V/μm), id4v(A/μm), bv(V; 없으면 생략)). n_wafers: 평균한 웨이퍼 수.
        prior_sigma: 기준값 쪽으로 당기는 가우시안 사전분포 폭, prior_laplace: 라플라스 사전분포 폭 b (노브 하나씩만 벗어나는 경우를 선호하는 희소 사전분포). 둘 다 없으면 균등.
        fine: 거친 격자(간격 0.025)로 사후분포를 구한 뒤 모인 영역을 0.005 간격으로 다시 계산한다."""
        obs = _obs(meas)

        def posterior(G, P, S):
            ll = _loglik(P, S, obs, n_wafers)
            if prior_sigma:
                ll = ll - 0.5 * (((G - 1) / prior_sigma) ** 2).sum(1)
            if prior_laplace:
                ll = ll - (np.abs(G - 1) / prior_laplace).sum(1)
            return _softmax(ll)

        G, P, S, mask = self.G, self.P, self.S, self.mask
        w = posterior(G, P, S)
        if fine:
            F = self._fine_grid(w)
            if F is not None:
                PF, SF = self.sur.raw_calibrated(F)
                G, P, S = F, PF, SF
                mask = ((np.abs(G - 1) > self.delta) @ np.array([1, 2, 4])).astype(int)
                w = posterior(G, P, S)
        r = self._summary(w, G, mask)
        r.update(측정=meas, 웨이퍼수=n_wafers, BV측정=3 in obs, 격자점수=int(len(G)), _w=w, _obs=obs, _G=G, _P=P, _S=S, _mask=mask)
        r["판정"] = ("판정: " + r["최다"]) if r["판정됨"] else "구분 불가"
        return r

    # ------------------------------------------------------------ 4) 다음 측정 권고
    def recommend(self, r, sims=60, extra_wafers=None):
        """후보 행동별로 사후분포에서 가상 진실을 뽑아 측정을 시뮬레이션하고, 판정 확률(최다 범주 확률)과 판정 가능 비율이 얼마나 오르는지 계산."""
        w, obs, n = r["_w"], r["_obs"], r["웨이퍼수"]
        G, P, S, mask = r["_G"], r["_P"], r["_S"], r["_mask"]
        extra = extra_wafers or n
        ll0 = _loglik(P, S, obs, n)
        acts = []
        if 3 not in obs:
            acts.append(("BV 측정 (같은 웨이퍼 수)", {3: NOISE["bv"]}, extra))
        acts.append((f"웨이퍼 {n}장 → {2 * n}장", {j: s for j, (_, s) in obs.items()}, n))
        acts.append((f"웨이퍼 {n}장 → {4 * n}장", {j: s for j, (_, s) in obs.items()}, 3 * n))
        truth = self.rng.choice(len(G), size=sims, p=w)
        out = []
        for name, noise, nn in acts:
            tops, dec, ok = [], 0, 0
            for i in truth:
                ynew = {j: (P[i, j] + self.rng.normal(0, s / np.sqrt(nn)), s) for j, s in noise.items()}
                wn = _softmax(ll0 + _loglik(P, S, ynew, nn))
                cat = self._cat(wn, mask)
                tops.append(cat.max())
                dec += cat.max() >= self.tau
                ok += (cat.argmax() == mask[i]) and cat.max() >= self.tau
            out.append(dict(행동=name, 기대최다확률=float(np.mean(tops)), 판정가능비율=dec / sims, 판정이맞을비율=ok / sims))
        cur = float(r["최다확률"])
        best = max(out, key=lambda a: (a["판정가능비율"], a["기대최다확률"]))
        if r["판정됨"]:
            msg = "추가 측정 불필요 (이미 판정됨)" if cur >= 0.9 else f"이미 판정됨(최다 확률 {100 * cur:.0f} %). 더 확실히 하려면 {best['행동']} (판정 가능 {100 * best['판정가능비율']:.0f} %)"
        else:
            msg = best["행동"] if best["판정가능비율"] > 0.05 + 0.0 else "추가 측정으로 크게 나아지지 않음"
        return dict(현재최다확률=cur, 행동들=out, 권고=msg)

    # ------------------------------------------------------------ 5) 보정안
    def compensate(self, r, limit=(0.85, 1.15), n=21, samples=100, tol=(0.10, 0.05, 0.05)):
        """에피는 못 바꾼다. 도즈·산화막 배율(한계 limit)을 사후분포 샘플 전체에서 기준값 특성(Vth, ln gm, ln Id)으로 되돌리는 쪽으로 고른다."""
        w = r["_w"]
        idx = self.rng.choice(len(r["_G"]), size=samples, p=w)
        X = r["_G"][idx]
        f = np.linspace(limit[0], limit[1], n)
        AD, AT = np.meshgrid(f, f, indexing="ij")
        A = np.c_[AD.ravel(), AT.ravel()]
        Xp = (X[None, :, :] * np.stack([A[:, 0], np.ones(len(A)), A[:, 1]], 1)[:, None, :]).reshape(-1, 3)
        P, S = self.sur.raw_calibrated(Xp)
        dom = self.sur.domain(Xp)
        t = np.array(tol)
        loss = (((P[:, :3] - self.base[:3]) / t) ** 2).sum(1)
        loss = np.where(dom, loss, 1e3).reshape(len(A), samples)
        L = loss.mean(1)
        i0 = int(np.argmin(np.abs(A[:, 0] - 1) + np.abs(A[:, 1] - 1)))          # 보정 안 함 (1, 1)
        ib = int(np.argmin(L))
        if L[ib] > 0.9 * L[i0]:
            ib = i0                                                             # 개선이 10 % 미만이면 건드리지 않는다 (불필요한 조정 방지)
        vth = P[:, 0].reshape(len(A), samples)
        bv = P[:, 3].reshape(len(A), samples)
        dm = dom.reshape(len(A), samples)
        spec = lambda i: float(np.mean((vth[i] >= SPEC["vth"][0]) & (vth[i] <= SPEC["vth"][1]) & dm[i]))
        q = lambda i: np.percentile(vth[i], [5, 50, 95]).tolist()
        pe = r["노브"][1]["벗어날확률"]
        return dict(도즈배율=float(A[ib, 0]), 산화막배율=float(A[ib, 1]), 손실_보정전=float(L[i0]), 손실_보정후=float(L[ib]), Vth_보정전_5_50_95=q(i0), Vth_보정후_5_50_95=q(ib),
                    Vth규격확률_보정전=spec(i0), Vth규격확률_보정후=spec(ib), BV규격확률=float(np.mean(bv[ib] >= SPEC["bv_min"])), 에피벗어날확률=pe,
                    경고=("에피가 벗어났을 가능성이 높다: 에피는 제어할 수 없어 BV 는 보정되지 않는다" if pe > 0.5 else None), 적용범위=limit)

    # ------------------------------------------------------------ 6) 고정밀 확인
    def final_check(self, r, prop=None, top_k=100, n_samples=20):
        """사후 상위 top_k 후보를 고정밀 모드로 다시 예측해 판정이 바뀌는지, 보정 후 상태가 규격 안에 드는지 확인한다."""
        if self.pipe is None or not getattr(self.pipe, "high_precision_available", False):
            return dict(실시=False, 사유="고정밀 모드를 쓸 수 없어 건너뜀 (기본 모드 결과 사용)")
        w, obs, n = r["_w"], r["_obs"], r["웨이퍼수"]
        G, mask = r["_G"], r["_mask"]
        t0 = time.perf_counter()
        idx = np.argsort(-w)[:top_k]
        Xs_ = G[idx]
        if prop:
            sel = self.rng.choice(len(G), size=n_samples, p=w)
            Xp = G[sel] * np.array([prop["도즈배율"], 1.0, prop["산화막배율"]])
            Xs_ = np.vstack([Xs_, Xp])                                         # 호출당 고정 비용이 커서 한 번에 묶어서 부른다
        hh = self.pipe.refine(Xs_, strict=False)
        k = len(idx)
        h = {key: (val[:k] if isinstance(val, np.ndarray) else val) for key, val in hh.items()}
        P2 = np.c_[h["vth"], np.log(h["gm"]), np.log(h["id4v"]), h["bv"]]
        S2 = np.c_[h["sigma_vth"], h["sigma_gm"], h["sigma_id4v"], h["sigma_bv"]]
        w2 = w.copy()
        w2[idx] = w[idx].sum() * _softmax(_loglik(P2, S2, obs, n))
        s2 = self._summary(w2 / w2.sum(), G, mask)
        out = dict(실시=True, 모드=hh["mode"], 후보수=int(k), 판정_전=r["최다"], 판정_후=s2["최다"], 최다확률_전=r["최다확률"], 최다확률_후=s2["최다확률"], 판정됨_후=s2["판정됨"], 판정바뀜=s2["최다"] != r["최다"])
        if prop:
            fast = self.sur.raw_calibrated(Xp)[0]
            hv = hh["vth"][k:]
            out["보정후_Vth_기본"] = float(np.median(fast[:, 0]))
            out["보정후_Vth_고정밀"] = float(np.median(hv))
            out["보정후_Vth규격확률_고정밀"] = float(np.mean((hv >= SPEC["vth"][0]) & (hv <= SPEC["vth"][1])))
        out["소요초"] = time.perf_counter() - t0
        return out

    # ------------------------------------------------------------ 전체 흐름
    def run(self, meas, n_wafers=1, check=True):
        r = self.diagnose(meas, n_wafers)
        rec = self.recommend(r)
        prop = self.compensate(r)
        fc = self.final_check(r, prop) if check else dict(실시=False, 사유="생략")
        mean = np.array([k["평균"] for k in r["노브"]])
        job = [dict(이름="보정 후 (사후 평균 상태)", 도즈=float(mean[0] * prop["도즈배율"]), 에피=float(mean[1]), 산화막=float(mean[2] * prop["산화막배율"])),
               dict(이름="보정 후 (가장 유력한 상태)", 도즈=float(r["MAP"][0] * prop["도즈배율"]), 에피=float(r["MAP"][1]), 산화막=float(r["MAP"][2] * prop["산화막배율"]))]
        return dict(진단=r, 다음측정=rec, 보정안=prop, 고정밀확인=fc, TCAD확인요청=job, 요약문=self.report(r, rec, prop, fc))

    def report(self, r, rec, prop, fc):
        L = [f"[측정] 웨이퍼 {r['웨이퍼수']}장 평균, BV {'측정함' if r['BV측정'] else '측정 안 함'}"]
        for k in r["노브"]:
            L.append(f"  {k['노브']}: 평균 {k['평균']:.3f} (90 % 구간 {k['구간90'][0]:.2f}~{k['구간90'][1]:.2f}), {self.delta * 100:.0f} % 넘게 벗어났을 확률 {100 * k['벗어날확률']:.0f} %")
        L.append(f"[판정] {r['판정']}  (가장 유력: {r['최다']} {100 * r['최다확률']:.0f} %; 기준 {100 * self.tau:.0f} %)")
        if not r["판정됨"]:
            L.append("  후보: " + ", ".join(f"{n} {100 * p:.0f} %" for n, p in r["후보"]))
        L.append(f"[다음 측정] {rec['권고']}  (" + "; ".join(f"{a['행동']}: 판정 가능 {100 * a['판정가능비율']:.0f} %" for a in rec["행동들"]) + ")")
        L.append(f"[보정안] 도즈 ×{prop['도즈배율']:.3f}, 산화막 ×{prop['산화막배율']:.3f} (에피는 제어 불가). Vth 규격 확률 {100 * prop['Vth규격확률_보정전']:.0f} % → {100 * prop['Vth규격확률_보정후']:.0f} %, BV 규격 확률 {100 * prop['BV규격확률']:.0f} %")
        if prop["경고"]:
            L.append("  주의: " + prop["경고"])
        if fc.get("실시"):
            L.append(f"[고정밀 확인] {fc['모드']}: 판정 {fc['판정_전']} → {fc['판정_후']}" + (" (바뀜)" if fc["판정바뀜"] else " (같음)") + f", {fc['소요초']:.1f}초")
        else:
            L.append(f"[고정밀 확인] {fc['사유']}")
        L.append("※ TCAD 합성 데이터로 학습한 서로게이트 기준. 보정안은 TCAD 확인 후에 쓴다.")
        return "\n".join(L)


def build_agent(high_precision=True):
    pipe = load_class("TwoStagePipeline")(high_precision="auto" if high_precision else False)
    return DiagnosisAgent(pipe.fast, pipe if high_precision else None), pipe


def demo():
    agent, pipe = build_agent()
    print(f"후보 격자 {len(agent.G)}개, 고정밀 {'가능' if pipe.high_precision_available else '불가'}")
    sur = pipe.fast
    for title, x, n, with_bv in [("산화막 +15 %", [1.0, 1.0, 1.15], 5, False), ("에피 −35 % (BV 있음)", [1.0, 0.65, 1.0], 5, True), ("도즈 +20 % 와 산화막 +8 %", [1.2, 1.0, 1.08], 25, True)]:
        y = sur.predict([x])
        meas = dict(vth=y["vth"][0], gm=y["gm"][0], id4v=y["id4v"][0], bv=y["bv"][0] if with_bv else None)
        rng = np.random.default_rng(7)
        meas["vth"] += rng.normal(0, NOISE["vth"] / np.sqrt(n))
        meas["gm"] *= 1 + rng.normal(0, NOISE["gm"] / np.sqrt(n))
        meas["id4v"] *= 1 + rng.normal(0, NOISE["id4v"] / np.sqrt(n))
        if with_bv:
            meas["bv"] += rng.normal(0, NOISE["bv"] / np.sqrt(n))
        t0 = time.perf_counter()
        res = agent.run(meas, n_wafers=n)
        print(f"\n=== 가상 이상: {title} (진짜 노브 {x}) — 전체 {time.perf_counter() - t0:.1f}초")
        print(res["요약문"])


def selftest():
    agent, _ = build_agent(high_precision=False)
    sur = agent.sur
    y = sur.predict([[1.0, 1.0, 1.0]])
    meas = dict(vth=y["vth"][0], gm=y["gm"][0], id4v=y["id4v"][0], bv=y["bv"][0])
    r = agent.diagnose(meas, n_wafers=100)                                       # 잡음 없이 기준값을 100장 평균으로 재면 정상이 가장 유력해야 한다
    assert abs(r["_w"].sum() - 1) < 1e-9 and r["최다"] == "정상" and r["최다확률"] > 0.5, (r["최다"], r["최다확률"])
    assert abs(sum(r["범주확률"].values()) - 1) < 1e-9
    y = sur.predict([[1.0, 0.6, 1.0]])
    m2 = dict(vth=y["vth"][0], gm=y["gm"][0], id4v=y["id4v"][0], bv=None)       # 에피만 −40 % 인데 BV 를 안 쟀다 → 구분 불가이고 BV 측정을 권해야 한다
    r2 = agent.diagnose(m2, n_wafers=5)
    rec = agent.recommend(r2, sims=30)
    assert not r2["판정됨"] and "BV" in rec["권고"], (r2["판정"], rec["권고"])
    m3 = dict(m2, bv=y["bv"][0])                                                  # BV 를 재면 에피가 벗어났다고 가리킬 수 있어야 한다
    r3 = agent.diagnose(m3, n_wafers=5)
    assert r3["노브"][1]["벗어날확률"] > 0.9, r3["노브"][1]
    p = agent.compensate(r3, samples=30, n=7)
    assert p["에피벗어날확률"] > 0.9 and p["경고"], p
    print("진단 에이전트 점검 통과")


if __name__ == "__main__":
    selftest()
    demo()

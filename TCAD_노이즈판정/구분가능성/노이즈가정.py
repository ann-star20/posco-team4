"""측정 잡음·정상 산포 가정값을 한 곳에서 관리하고, TCAD 결과에 잡음을 입히는 함수.

원칙: TCAD 결과(CSV)는 깨끗하게 저장하고, 잡음은 학습·평가할 때 여기서 입힌다.
      가정을 바꾸려면 이 파일의 NOISE, SIGMA_LOT_PCT만 고치면 된다. 모든 숫자는 **가정값**이다.
"""
import numpy as np

# 출력별 측정 잡음 1σ (가정). ("abs", 값) = 더하는 잡음(출력 단위), ("rel", 비율) = 곱하는 잡음(0.05 = 5 %)
NOISE = {
    "vth":    ("abs", 0.050),   # V      프로젝트 기존 가정 (근거 없음)
    "gm":     ("rel", 0.05),    #        Id(4V)와 같게 둠 (근거 없음)
    "id_4v":  ("rel", 0.05),    #        프로젝트 기존 가정 (근거 없음)
    "id_vd4": ("rel", 0.05),    #        Id(4V)와 같게 둠 (근거 없음)
    "bv":     ("abs", 0.3),     # V      메쉬 시험의 BV 허용 기준
}
SIGMA_LOT_PCT = 3.0             # 정상 로트 간 산포 1σ, 노브당 % (가정, 평균해도 안 줄어듦)
SCALE_RANGE = (0.5, 2.0)        # 학습 때 잡음 크기를 뽑는 범위 (가정이 틀려도 버티게 하려는 용도)
# ponytail: 출력끼리 독립인 가우시안만 다룸. 장비 오프셋·드리프트·출력 간 상관은 모델 밖 (다이를 평균해도 안 줄어드는 오차)


def add_noise(y, scale=1.0, n_avg=1, rng=None):
    """y(출력 이름 → 값 또는 배열)에 가정 잡음을 입힌 사본을 돌려준다.

    scale : 가정 잡음의 배수 (0이면 그대로). n_avg : 다이 평균 개수, 잡음이 1/sqrt(n_avg)로 줄어든다.
    NOISE에 없는 키(노브 비율, 온저항 등)는 건드리지 않는다.
    """
    rng = rng or np.random.default_rng()
    out = dict(y)
    for key, (kind, sigma) in NOISE.items():
        if key not in y:
            continue
        eps = rng.normal(0.0, sigma * scale / np.sqrt(n_avg), size=np.shape(y[key]))
        out[key] = y[key] + eps if kind == "abs" else y[key] * (1 + eps)
    return out


def random_scale(rng, lo=SCALE_RANGE[0], hi=SCALE_RANGE[1]):
    """학습 샘플마다 잡음 배수를 로그 균등으로 뽑는다 (add_noise(..., scale=random_scale(rng)))."""
    return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))


def sigma_analysis(order=("vth", "gm", "id_4v", "id_vd4", "bv"), scale=1.0):
    """구분 가능성 분석의 출력 단위(Vth mV, 전류·gm %, BV V)로 바꾼 잡음 1σ 배열."""
    unit = {"vth": 1000.0}                                   # V → mV
    return np.array([NOISE[k][1] * scale * unit.get(k, 100.0 if NOISE[k][0] == "rel" else 1.0) for k in order])


def describe():
    """결과 문서에 적을 가정값 설명 한 줄."""
    return (f"Vth {NOISE['vth'][1] * 1000:.0f} mV, gm {NOISE['gm'][1] * 100:.0f} %, Id(4V) {NOISE['id_4v'][1] * 100:.0f} %, "
            f"Id(Vd=4V) {NOISE['id_vd4'][1] * 100:.0f} %, BV {NOISE['bv'][1]} V")


if __name__ == "__main__":                                   # 점검: python 노이즈가정.py
    rng = np.random.default_rng(0)
    y = {"vth": np.full(20000, 2.26), "gm": np.full(20000, 4.6e-6), "bv": np.full(20000, 41.0), "tox": np.full(20000, 1.0)}
    assert all(np.array_equal(add_noise(y, 0, rng=rng)[k], y[k]) for k in y)                  # scale 0이면 그대로
    z = add_noise(y, rng=rng)
    assert abs(z["vth"].std() - 0.05) < 0.002 and abs(z["gm"].std() / 4.6e-6 - 0.05) < 0.002  # 가정한 크기
    assert np.array_equal(z["tox"], y["tox"])                                                 # 목록에 없는 키는 그대로
    assert abs(add_noise(y, n_avg=16, rng=rng)["bv"].std() - 0.3 / 4) < 0.01                  # 평균하면 1/sqrt(N)
    assert all(SCALE_RANGE[0] <= random_scale(rng) <= SCALE_RANGE[1] for _ in range(1000))
    assert np.allclose(sigma_analysis(), [50, 5, 5, 5, 0.3])                                  # 분석 스크립트가 쓰는 단위
    print("노이즈가정 점검 통과:", describe())

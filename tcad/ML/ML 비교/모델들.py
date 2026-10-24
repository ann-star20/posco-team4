"""서로게이트 후보 모델. 모두 fit_predict(Xtr, Ytr, Xte) -> (P, S) 형태. 입력은 기준 대비 비율(n×3), Ytr 은 n×4 (Vth, ln gm, ln Id(4V), BV; BV 는 NaN 가능).
출력 P, S 는 n×4 (S 는 모델이 낸 불확실도, 없으면 NaN).
후보:
  1 현재 2단GP        : 간의 TCAD 에서 쓰는 모델 (Vth·gm·BV 각각 GP, Id 는 Vth 예측을 입력에 더한 2단 GP, 잡음항 상한 1e-2)
  2 2단GP 개선        : 1 + 잡음항 상한 1.0 + BV 는 원래 입력 GP (사전 시험에서 BV 0.154 V)
  3 추세+GP           : 2차 다항식 추세를 빼고 남은 잔차를 GP 로 (외삽에서 추세가 받쳐 준다)
  4 다중출력GP        : Vth·gm·Id 를 하나의 GP(ICM, 출력 간 상관을 학습)로, BV 는 2 의 BV
  5 딥GP(2층)         : gpytorch 2층 딥 GP, 출력마다 하나
  6 MLP 앙상블        : 5개 MLP(64×2, SiLU) 앙상블, 4 출력을 한 네트워크로. Jetson/TensorRT 에 올리기 쉬움
  7 LightGBM          : 트리 부스팅 (참고용)
"""
import numpy as np

from 공통 import ev, phys

M0 = ev.models()


def _gp(d, wide):
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel as C, Matern, WhiteKernel
    return GaussianProcessRegressor(C(1.0) * Matern([0.5] * d, nu=2.5, length_scale_bounds=(0.05, 20)) + WhiteKernel(1e-3 if wide else 1e-6, (1e-10, 1.0 if wide else 1e-2)),
                                    normalize_y=True, n_restarts_optimizer=3, random_state=0)


def _two_stage(Xtr, Ytr, Xte, wide, bv_raw, trend=False):
    P, S = np.zeros((len(Xte), 4)), np.full((len(Xte), 4), np.nan)
    f, ft = phys(Xtr), phys(Xte)
    vth_hat = None

    def fit_pred(F, y, Ft):
        if trend:
            from sklearn.linear_model import Ridge
            from sklearn.preprocessing import PolynomialFeatures
            pf = PolynomialFeatures(2, include_bias=False)
            A, At = pf.fit_transform(F), pf.transform(Ft)
            r = Ridge(alpha=1e-6).fit(A, y)
            g = _gp(F.shape[1], wide).fit(F, y - r.predict(A))
            m, s = g.predict(Ft, return_std=True)
            return m + r.predict(At), s
        g = _gp(F.shape[1], wide).fit(F, y)
        return g.predict(Ft, return_std=True)

    for j in range(4):
        ok = ~np.isnan(Ytr[:, j])
        if j == 2:
            p, s = fit_pred(np.c_[f[ok], Ytr[ok, 0]], Ytr[ok, 2], np.c_[ft, vth_hat])
        elif j == 3 and bv_raw:
            p, s = fit_pred(Xtr[ok], Ytr[ok, 3], Xte)
        else:
            p, s = fit_pred(f[ok], Ytr[ok, j], ft)
        if j == 0:
            vth_hat = p
        P[:, j], S[:, j] = p, s
    return P, S


def m1(Xtr, Ytr, Xte):
    return ev.predict_all(M0, "2단GP", Xtr, Ytr, Xte)


def m2(Xtr, Ytr, Xte):
    return _two_stage(Xtr, Ytr, Xte, wide=True, bv_raw=True)


def m3(Xtr, Ytr, Xte):
    return _two_stage(Xtr, Ytr, Xte, wide=True, bv_raw=True, trend=True)


# ---------------------------------------------------------------- 다중출력 GP (gpytorch ICM)
def m4(Xtr, Ytr, Xte):
    import gpytorch
    import torch
    torch.manual_seed(0)
    f, ft = phys(Xtr), phys(Xte)
    mu, sd = f.mean(0), f.std(0)
    Y = Ytr[:, :3]
    ym, ys = Y.mean(0), Y.std(0)
    Xt = torch.tensor((f - mu) / sd, dtype=torch.float64)
    Yt = torch.tensor((Y - ym) / ys, dtype=torch.float64)
    lik = gpytorch.likelihoods.MultitaskGaussianLikelihood(num_tasks=3, noise_constraint=gpytorch.constraints.GreaterThan(1e-8))

    class ICM(gpytorch.models.ExactGP):
        def __init__(s, x, y, l):
            super().__init__(x, y, l)
            s.mean_module = gpytorch.means.MultitaskMean(gpytorch.means.ConstantMean(), num_tasks=3)
            s.covar_module = gpytorch.kernels.MultitaskKernel(gpytorch.kernels.MaternKernel(nu=2.5, ard_num_dims=3), num_tasks=3, rank=3)

        def forward(s, x):
            return gpytorch.distributions.MultitaskMultivariateNormal(s.mean_module(x), s.covar_module(x))
    model = ICM(Xt, Yt, lik).double()
    lik.double()
    model.train(), lik.train()
    opt = torch.optim.Adam(model.parameters(), lr=0.1)
    mll = gpytorch.mlls.ExactMarginalLogLikelihood(lik, model)
    with gpytorch.settings.cholesky_jitter(1e-6):
        for _ in range(250):
            opt.zero_grad()
            loss = -mll(model(Xt), Yt)
            loss.backward()
            opt.step()
        model.eval(), lik.eval()
        with torch.no_grad():
            pr = lik(model(torch.tensor((ft - mu) / sd, dtype=torch.float64)))
            m, s = pr.mean.numpy() * ys + ym, pr.stddev.numpy() * ys
    P, S = np.zeros((len(Xte), 4)), np.full((len(Xte), 4), np.nan)
    P[:, :3], S[:, :3] = m, s
    ok = ~np.isnan(Ytr[:, 3])
    g = _gp(3, True).fit(Xtr[ok], Ytr[ok, 3])
    P[:, 3], S[:, 3] = g.predict(Xte, return_std=True)
    return P, S


# ---------------------------------------------------------------- 딥 GP (gpytorch, 2층)
def _dgp_fit_predict(F, y, Ft, epochs=800, seed=0):
    import gpytorch
    import torch
    from gpytorch.models.deep_gps import DeepGP, DeepGPLayer
    from gpytorch.variational import CholeskyVariationalDistribution, VariationalStrategy
    torch.manual_seed(seed)
    mu, sd = F.mean(0), F.std(0)
    ym, ys = y.mean(), y.std()
    X = torch.tensor((F - mu) / sd, dtype=torch.float32)
    Y = torch.tensor((y - ym) / ys, dtype=torch.float32)
    d = F.shape[1]
    nind = min(48, len(X))

    class Layer(DeepGPLayer):
        def __init__(s, din, dout, mean_type):
            if dout is None:
                ind, bs = torch.randn(nind, din), torch.Size([])
            else:
                ind, bs = X[torch.randperm(len(X))[:nind]].clone().unsqueeze(0).repeat(dout, 1, 1), torch.Size([dout])
            vd = CholeskyVariationalDistribution(nind, batch_shape=bs)
            vs = VariationalStrategy(s, ind, vd, learn_inducing_locations=True)
            super().__init__(vs, din, dout)
            s.mean_module = gpytorch.means.ConstantMean() if mean_type == "constant" else gpytorch.means.LinearMean(din)
            s.covar_module = gpytorch.kernels.ScaleKernel(gpytorch.kernels.MaternKernel(nu=2.5, batch_shape=bs, ard_num_dims=din), batch_shape=bs)

        def forward(s, x):
            return gpytorch.distributions.MultivariateNormal(s.mean_module(x), s.covar_module(x))

    class DGP(DeepGP):
        def __init__(s):
            super().__init__()
            s.hidden = Layer(d, d, "linear")
            s.last = Layer(d, None, "constant")
            s.likelihood = gpytorch.likelihoods.GaussianLikelihood()

        def forward(s, x):
            return s.last(s.hidden(x))

    model = DGP()
    model.train()
    opt = torch.optim.Adam(model.parameters(), lr=0.02)
    mll = gpytorch.mlls.DeepApproximateMLL(gpytorch.mlls.VariationalELBO(model.likelihood, model, num_data=len(X)))
    for _ in range(epochs):
        opt.zero_grad()
        loss = -mll(model(X), Y)
        loss.backward()
        opt.step()
    model.eval()
    with torch.no_grad(), gpytorch.settings.num_likelihood_samples(30):
        pr = model.likelihood(model(torch.tensor((Ft - mu) / sd, dtype=torch.float32)))
        m = pr.mean.mean(0).numpy()
        v = pr.variance.mean(0).numpy() + pr.mean.var(0).numpy()
    return m * ys + ym, np.sqrt(v) * ys


def m5(Xtr, Ytr, Xte):
    P, S = np.zeros((len(Xte), 4)), np.full((len(Xte), 4), np.nan)
    f, ft = phys(Xtr), phys(Xte)
    for j in range(4):
        ok = ~np.isnan(Ytr[:, j])
        P[:, j], S[:, j] = _dgp_fit_predict(f[ok], Ytr[ok, j], ft)
    return P, S


# ---------------------------------------------------------------- MLP 앙상블 (torch)
class MLPEns:
    def __init__(self, n=5, hidden=128, epochs=5000, kind="mlp"):
        self.n, self.h, self.ep, self.kind = n, hidden, epochs, kind

    def fit(self, X, Y):
        import torch
        f = phys(X)
        self.mu, self.sd = f.mean(0), f.std(0)
        self.ym, self.ys = np.nanmean(Y, 0), np.nanstd(Y, 0)
        Xt = torch.tensor((f - self.mu) / self.sd, dtype=torch.float32)
        Yn = (Y - self.ym) / self.ys
        mask = torch.tensor(~np.isnan(Yn), dtype=torch.float32)
        Yt = torch.tensor(np.nan_to_num(Yn), dtype=torch.float32)
        self.nets = []
        for k in range(self.n):
            torch.manual_seed(k)
            if self.kind == "nvidia":                      # NVIDIA PhysicsNeMo 의 FullyConnected (skip 연결 + 적응형 활성함수 + 가중치 분해)
                from physicsnemo.models.mlp import FullyConnected
                net = FullyConnected(in_features=3, layer_size=self.h, out_features=4, num_layers=3, activation_fn="silu", skip_connections=True, adaptive_activations=True, weight_fact=True)
            else:
                net = torch.nn.Sequential(torch.nn.Linear(3, self.h), torch.nn.SiLU(), torch.nn.Linear(self.h, self.h), torch.nn.SiLU(), torch.nn.Linear(self.h, 4))
            opt = torch.optim.Adam(net.parameters(), lr=3e-3, weight_decay=1e-6)
            sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, self.ep)
            for _ in range(self.ep):
                opt.zero_grad()
                loss = (((net(Xt) - Yt) ** 2) * mask).sum() / mask.sum()
                loss.backward()
                opt.step()
                sch.step()
            self.nets.append(net.eval())
        return self

    def predict(self, X):
        import torch
        Xt = torch.tensor((phys(X) - self.mu) / self.sd, dtype=torch.float32)
        with torch.no_grad():
            p = np.array([n(Xt).numpy() for n in self.nets]) * self.ys + self.ym
        return p.mean(0), p.std(0)


def m6(Xtr, Ytr, Xte):
    return MLPEns().fit(Xtr, Ytr).predict(Xte)


# ---------------------------------------------------------------- LightGBM
def m7(Xtr, Ytr, Xte):
    import lightgbm as lgb
    P, S = np.zeros((len(Xte), 4)), np.full((len(Xte), 4), np.nan)
    for j in range(4):
        ok = ~np.isnan(Ytr[:, j])
        m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=8, min_child_samples=3, subsample=1.0, verbose=-1).fit(Xtr[ok], Ytr[ok, j])
        P[:, j] = m.predict(Xte)
    return P, S


def m8(Xtr, Ytr, Xte):
    return MLPEns(n=3, epochs=3000, kind="nvidia").fit(Xtr, Ytr).predict(Xte)


# ---------------------------------------------------------------- TabPFN v2 (표 데이터용 사전학습 모델, 로그인·키 불필요, Apache 2.0 + 출처 표기)
def _tabpfn(F, y, Ft):
    """출력 하나를 TabPFN v2 로 예측: 평균, 불확실도 = (84 % 분위수 − 16 % 분위수)/2"""
    from tabpfn import TabPFNRegressor
    from tabpfn.constants import ModelVersion
    m = TabPFNRegressor.create_default_for_version(ModelVersion.V2, device="cpu").fit(F, y)
    q = np.asarray(m.predict(Ft, output_type="quantiles", quantiles=[0.1587, 0.5, 0.8413]))
    return m.predict(Ft), np.maximum((q[2] - q[0]) / 2, 1e-12)


def _tab_all(Xtr, Ytr, Xte, inp="phys", trend=False, two_stage=False):
    P, S = np.zeros((len(Xte), 4)), np.full((len(Xte), 4), np.nan)
    f, ft = (phys(Xtr), phys(Xte)) if inp == "phys" else (Xtr, Xte)
    vth_hat = None
    for j in range(4):
        ok = ~np.isnan(Ytr[:, j])
        F, Ft = f[ok], ft
        if two_stage and j == 2:
            F, Ft = np.c_[F, Ytr[ok, 0]], np.c_[ft, vth_hat]
        if trend:
            from sklearn.linear_model import Ridge
            from sklearn.preprocessing import PolynomialFeatures
            pf = PolynomialFeatures(2, include_bias=False)
            A, At = pf.fit_transform(F), pf.transform(Ft)
            r = Ridge(alpha=1e-6).fit(A, Ytr[ok, j])
            p, s = _tabpfn(F, Ytr[ok, j] - r.predict(A), Ft)
            p = p + r.predict(At)
        else:
            p, s = _tabpfn(F, Ytr[ok, j], Ft)
        if j == 0:
            vth_hat = p
        P[:, j], S[:, j] = p, s
    return P, S


def m9(Xtr, Ytr, Xte):
    return _tab_all(Xtr, Ytr, Xte)


def m10(Xtr, Ytr, Xte):
    return _tab_all(Xtr, Ytr, Xte, trend=True)


def m11(Xtr, Ytr, Xte):
    return _tab_all(Xtr, Ytr, Xte, two_stage=True)


def m12(Xtr, Ytr, Xte):
    P1, S1 = _tab_all(Xtr, Ytr, Xte, inp="phys", two_stage=True)
    P2, S2 = _tab_all(Xtr, Ytr, Xte, inp="raw", two_stage=True)
    P = (P1 + P2) / 2
    return P, np.sqrt((S1 ** 2 + S2 ** 2) / 2 + ((P1 - P2) / 2) ** 2)



# ---------------------------------------------------------------- GP + TabPFN 결합
CAL_GP = np.array([0.91, 0.89, 1.69, 1.68])      # 교차검증으로 구한 GP(개선) σ 보정 배율 (오차÷σ 의 RMS)


def m13(Xtr, Ytr, Xte):
    """정밀도 가중 평균: 두 모델의 보정된 σ 의 역제곱으로 가중 (GP = 개선 2단 GP, TabPFN = 2단 v2)"""
    Pg, Sg = m2(Xtr, Ytr, Xte)
    Pt, St = m11(Xtr, Ytr, Xte)
    wg, wt = 1 / (Sg * CAL_GP) ** 2, 1 / St ** 2
    P = (wg * Pg + wt * Pt) / (wg + wt)
    return P, np.sqrt(1 / (wg + wt))


def m14(Xtr, Ytr, Xte):
    """스태킹: GP 의 교차예측 잔차(보지 않은 점에서 GP 가 틀리는 부분)를 TabPFN 이 배워 GP 예측에 더한다"""
    from sklearn.model_selection import KFold
    Pg, Sg = m2(Xtr, Ytr, Xte)
    R = np.full_like(Ytr, np.nan)
    for a, b in KFold(5, shuffle=True, random_state=0).split(Xtr):
        Po, _ = m2(Xtr[a], Ytr[a], Xtr[b])
        R[b] = Ytr[b] - Po
    f, ft = phys(Xtr), phys(Xte)
    P = Pg.copy()
    for j in range(4):
        ok = ~np.isnan(R[:, j])
        P[:, j] = Pg[:, j] + _tabpfn(f[ok], R[ok, j], ft)[0]
    return P, Sg



# ---------------------------------------------------------------- BV 전용 입력 변환 시험 (도즈는 원래 값, 에피는 로그, 산화막은 원래 값)
def _bv_variant(Xtr, Ytr, Xte, logy):
    P, S = m2(Xtr, Ytr, Xte)                                   # Vth·gm·Id 는 2번(2단 GP 개선)과 같다
    ok = ~np.isnan(Ytr[:, 3])
    F = lambda X: np.c_[X[:, 0], np.log(X[:, 1]), X[:, 2]]
    y = np.log(Ytr[ok, 3]) if logy else Ytr[ok, 3]
    g = _gp(3, True).fit(F(Xtr[ok]), y)
    m, s = g.predict(F(Xte), return_std=True)
    P[:, 3], S[:, 3] = (np.exp(m), np.exp(m) * s) if logy else (m, s)
    return P, S


def m15(Xtr, Ytr, Xte):
    return _bv_variant(Xtr, Ytr, Xte, False)


def m16(Xtr, Ytr, Xte):
    return _bv_variant(Xtr, Ytr, Xte, True)


MODELS = {"1 현재 2단GP": (m1, False), "2 2단GP 개선": (m2, False), "3 추세+GP": (m3, False), "4 다중출력GP": (m4, False), "5 딥GP(2층)": (m5, True), "6 MLP앙상블": (m6, False), "7 LightGBM": (m7, False), "8 PhysicsNeMo FC앙상블": (m8, False), "9 TabPFN v2": (m9, False), "10 TabPFN+추세": (m10, False), "11 TabPFN 2단": (m11, False), "12 TabPFN 입력앙상블": (m12, False), "13 GP+TabPFN 가중평균": (m13, False), "14 GP+TabPFN 잔차": (m14, False), "15 BV전용변환 GP": (m15, False), "16 BV전용변환+ln BV": (m16, False)}

import math
import numpy as np
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64
from scipy.optimize import differential_evolution
import os

# Configuration pour charger le modèle
def get_model_path(filename):
    return os.path.join(os.path.dirname(__file__), filename)

def _load_ann_model():
    """Charge ann_model.pkl, ann_scaler.pkl, ann_transform.pkl."""
    model     = joblib.load(get_model_path("ann_model.pkl"))
    scaler    = joblib.load(get_model_path("ann_scaler.pkl"))
    transform = joblib.load(get_model_path("ann_transform.pkl"))
    return model, scaler, transform['uz_log']

def _predict_uz(model, scaler, uz_log, C, phi, B, A_r, h_r, e_r, Lx_r, N, EA, q):
    q_log   = np.log1p(q)
    x_input = np.array([[C, phi, B, A_r, h_r, e_r, Lx_r, N, EA, q_log]])
    x_sc    = scaler.transform(x_input)
    pred    = model.predict(x_sc)[0]
    uz      = np.expm1(pred) if uz_log else pred
    return max(float(uz), 0.0)

def _geogrid_area(B, A_abs, Lx_abs, N):
    return N * (A_abs + 2.0 * Lx_abs) * (B + 2.0 * Lx_abs)

def _sweep_and_find_qult(model, scaler, uz_log, C, phi, B, A_r, h_r, e_r, Lx_r, N, EA, FS, q_max=200_000.0, n_points=300):
    UZ_CRIT  = 0.1  * B
    UZ_STOP  = 0.15 * B
    q_values = np.linspace(0.0, q_max, n_points)
    q_list, uz_list = [], []

    for q_val in q_values:
        uz = _predict_uz(model, scaler, uz_log, C, phi, B, A_r, h_r, e_r, Lx_r, N, EA, q_val)
        q_list.append(q_val)
        uz_list.append(uz)
        if uz >= UZ_STOP:
            break

    q_arr  = np.array(q_list)
    uz_arr = np.array(uz_list)

    idx              = np.searchsorted(uz_arr, UZ_CRIT)
    critere_atteint  = True

    if idx == 0:
        q_ult_SGR = float(q_arr[0])
    elif idx >= len(uz_arr):
        dq = q_arr[-1] - q_arr[-2]
        du = uz_arr[-1] - uz_arr[-2]
        slope = du / max(dq, 1.0e-9)
        q_ult_SGR       = (q_arr[-1] + (UZ_CRIT - uz_arr[-1]) / max(slope, 1.0e-12) if abs(slope) > 1.0e-12 else float(q_arr[-1]))
        critere_atteint = False
    else:
        q1, q2    = q_arr[idx-1], q_arr[idx]
        u1, u2    = uz_arr[idx-1], uz_arr[idx]
        q_ult_SGR = q1 + (UZ_CRIT - u1) * (q2 - q1) / max(u2 - u1, 1.0e-12)

    q_ad_SGR = float(q_ult_SGR) / FS
    return float(q_ult_SGR), q_ad_SGR, q_arr, uz_arr, critere_atteint

def solve_module1(C, phi, gamma, B, L, Df, F, FS):
    phi_rad = math.radians(phi)
    Nq = (math.exp(math.pi * math.tan(phi_rad)) * math.tan(math.radians(45) + phi_rad / 2) ** 2)
    Nc = 5.14 if phi == 0 else (Nq - 1) / math.tan(phi_rad)
    Ng = 2.0 * (Nq + 1) * math.tan(phi_rad)

    Sc = 1.0 + 0.2 * (B / L)
    Sq = 1.0
    Sg = 1.0 - 0.2 * (B / L)

    q0              = gamma * Df
    terme_gamma     = 0.5 * Sg * gamma * B * Ng
    terme_surcharge = Sq * q0 * Nq
    terme_cohesion  = Sc * C * Nc
    q_ult_brut      = terme_gamma + terme_surcharge + terme_cohesion
    q_net_ult       = q_ult_brut - q0

    footing_area = B * L
    q_app = F / footing_area
    q_net_admissible = q_net_ult / FS
    q_ad = q_net_admissible + q0

    return {
        'C': C, 'phi': phi, 'gamma': gamma,
        'B': B, 'L': L, 'L_ratio': L / B, 'Df': Df,
        'F': F, 'FS': FS,
        'footing_area': footing_area,
        'q_app': q_app,
        'q_ad': q_ad,
        'q_net_ult': q_net_ult,
        'q_ult_brut': q_ult_brut,
        'q0': q0,
        'Nq': Nq, 'Nc': Nc, 'Ng': Ng,
        'Sc': Sc, 'Sq': Sq, 'Sg': Sg,
        'terme_gamma': terme_gamma,
        'terme_surcharge': terme_surcharge,
        'terme_cohesion': terme_cohesion,
        'needs_grs': q_app > q_ad,
        'deficit': max(0, q_app - q_ad)
    }

def solve_module3(grs_data, EA, UZ_ALLOW):
    C        = grs_data['C']
    phi      = grs_data['phi']
    B        = grs_data['B']
    A_abs    = grs_data['L']
    A_r      = grs_data['L_ratio']
    q_target = grs_data['q_app']
    FS       = grs_data['FS']
    UZ_LIMIT = UZ_ALLOW / 1000.0

    model, scaler, uz_log = _load_ann_model()

    TOL_M   = 0.10 / 1000.0
    PENALTY = 1.0e8

    H_R_MIN  = max(0.1, 0.15 / B)
    H_R_MAX  = 0.6
    E_R_MIN  = max(0.1, 0.10 / B)
    E_R_MAX  = 0.6
    LX_R_MIN = 0.5
    LX_R_MAX = 3.0
    N_MIN, N_MAX = 1, 7

    def _pred(h_r, e_r, Lx_r, N):
        return _predict_uz(model, scaler, uz_log, C, phi, B, A_r, h_r, e_r, Lx_r, N, EA, q_target)

    def _find_qad(h_r, e_r, Lx_r, N):
        _, q_ad, _, _, _ = _sweep_and_find_qult(
            model, scaler, uz_log, C, phi, B, A_r, h_r, e_r, Lx_r, N, EA, FS, q_max=200_000.0, n_points=200)
        return q_ad

    # Pre-feasibility sweep
    h_vals  = np.linspace(H_R_MIN,  H_R_MAX,  6)
    e_vals  = np.linspace(E_R_MIN,  E_R_MAX,  6)
    lx_vals = np.linspace(LX_R_MIN, LX_R_MAX, 6)
    uz_min_grille = np.inf
    elu_faisable  = False

    for h_r in h_vals:
        for e_r in e_vals:
            for lx_r in lx_vals:
                for N in range(N_MIN, N_MAX + 1):
                    uz = _pred(h_r, e_r, lx_r, N)
                    if uz < uz_min_grille: uz_min_grille = uz
                    if uz <= UZ_LIMIT + TOL_M:
                        q_ad = _find_qad(h_r, e_r, lx_r, N)
                        if q_target <= q_ad: elu_faisable = True

    if uz_min_grille > UZ_LIMIT + TOL_M:
        return {'success': False, 'message': "Le SGR NE PEUT PAS satisfaire l'exigence de tassement dans le domaine d'entraînement de l'ANN."}

    BORNES_4D = [(H_R_MIN, H_R_MAX), (E_R_MIN, E_R_MAX), (LX_R_MIN, LX_R_MAX), (float(N_MIN), float(N_MAX))]

    def _objectif_4d(x):
        h_r, e_r, Lx_r, N_cont = x
        N        = max(N_MIN, round(N_cont))
        uz       = _pred(h_r, e_r, Lx_r, N)
        surface  = _geogrid_area(B, A_abs, Lx_r * B, N)
        q_ad     = _find_qad(h_r, e_r, Lx_r, N)
        viol_els = max(0.0, uz       - UZ_LIMIT - TOL_M)
        viol_elu = max(0.0, q_target - q_ad)
        return surface + PENALTY * viol_els ** 2 + PENALTY * viol_elu ** 2

    result_4d = differential_evolution(
        _objectif_4d, bounds=BORNES_4D, strategy='best1bin', maxiter=500, popsize=20,
        tol=1e-10, mutation=(0.5, 1.0), recombination=0.7, seed=42, polish=True, disp=False
    )

    N_etape1 = max(N_MIN, round(result_4d.x[3]))

    if N_etape1 == 1:
        def _objectif_1d(lx_arr):
            lx_r     = lx_arr[0]
            uz       = _pred(H_R_MIN, E_R_MIN, lx_r, 1)
            surface  = _geogrid_area(B, A_abs, lx_r * B, 1)
            q_ad     = _find_qad(H_R_MIN, E_R_MIN, lx_r, 1)
            viol_els = max(0.0, uz       - UZ_LIMIT - TOL_M)
            viol_elu = max(0.0, q_target - q_ad)
            return surface + PENALTY * viol_els ** 2 + PENALTY * viol_elu ** 2

        result_1d = differential_evolution(
            _objectif_1d, bounds=[(LX_R_MIN, LX_R_MAX)], strategy='best1bin', maxiter=500,
            popsize=20, tol=1e-10, mutation=(0.5, 1.0), recombination=0.7, seed=42, polish=True, disp=False
        )
        h_r_opt, e_r_opt, Lx_r_opt, N_opt = H_R_MIN, E_R_MIN, float(result_1d.x[0]), 1
    else:
        h_r_opt, e_r_opt, Lx_r_opt, N_opt = float(result_4d.x[0]), float(result_4d.x[1]), float(result_4d.x[2]), N_etape1

    if _pred(h_r_opt, e_r_opt, Lx_r_opt, N_opt) > UZ_LIMIT + TOL_M:
        meilleure_surface = np.inf
        meilleures_vars   = (H_R_MIN, E_R_MIN, LX_R_MAX, N_MAX)
        for h_r  in np.linspace(H_R_MIN,  H_R_MAX,  10):
            for e_r  in np.linspace(E_R_MIN,  E_R_MAX,  10):
                for lx_r in np.linspace(LX_R_MIN, LX_R_MAX, 10):
                    for N in range(N_MIN, N_MAX + 1):
                        if _pred(h_r, e_r, lx_r, N) <= UZ_LIMIT + TOL_M:
                            surf = _geogrid_area(B, A_abs, lx_r * B, N)
                            if surf < meilleure_surface:
                                meilleure_surface = surf
                                meilleures_vars   = (h_r, e_r, lx_r, N)
        h_r_opt, e_r_opt, Lx_r_opt, N_opt = meilleures_vars
        N_opt = int(N_opt)

    h_opt  = h_r_opt  * B
    e_opt  = e_r_opt  * B
    Lx_opt = Lx_r_opt * B
    uz_opt    = _pred(h_r_opt, e_r_opt, Lx_r_opt, N_opt)
    q_ad_opt  = _find_qad(h_r_opt, e_r_opt, Lx_r_opt, N_opt)
    surface_opt = _geogrid_area(B, A_abs, Lx_opt, N_opt)
    els_ok    = uz_opt    <= UZ_LIMIT + TOL_M
    ELU_TOL   = 1.0
    elu_ok    = q_target  <= q_ad_opt + ELU_TOL

    long_couche = A_abs + 2.0 * Lx_opt
    larg_couche = B     + 2.0 * Lx_opt
    surf_couche = long_couche * larg_couche

    # MODULE 3B
    uz_crit = 0.1 * B
    UZ_STOP = 0.2 * B
    q_values = np.linspace(0.0, 200_000.0, 500)
    q_list, uz_list = [], []

    for q_val in q_values:
        uz = _predict_uz(model, scaler, uz_log, C, phi, B, A_r, h_r_opt, e_r_opt, Lx_r_opt, N_opt, EA, q_val)
        q_list.append(q_val)
        uz_list.append(uz)
        if uz >= UZ_STOP: break

    q_arr = np.array(q_list)
    uz_arr = np.array(uz_list)
    uz_arr_mm = uz_arr * 1000.0

    idx = np.searchsorted(uz_arr, uz_crit)
    critere_atteint = True
    if idx == 0:
        q_ult_SGR = float(q_arr[0])
    elif idx >= len(uz_arr):
        dq = q_arr[-1] - q_arr[-2]
        du = uz_arr[-1] - uz_arr[-2]
        slope = du / max(dq, 1.0e-9)
        q_ult_SGR = (q_arr[-1] + (uz_crit - uz_arr[-1]) / max(slope, 1.0e-12) if abs(slope) > 1.0e-12 else float(q_arr[-1]))
        critere_atteint = False
    else:
        q1, q2 = q_arr[idx-1], q_arr[idx]
        u1, u2 = uz_arr[idx-1], uz_arr[idx]
        q_ult_SGR = q1 + (uz_crit - u1) * (q2 - q1) / max(u2 - u1, 1.0e-12)

    q_ad_SGR = q_ult_SGR / FS
    els_ok_final = uz_opt  <= UZ_LIMIT + TOL_M
    elu_ok_final = q_target  <= q_ad_SGR

    # Draw plot
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(q_arr / 1000.0, uz_arr_mm, color='#1a6faf', linewidth=2.5, label="Courbe Charge-Tassement SGR", zorder=3)
    ax.axhline(UZ_LIMIT * 1000, color='#e07b39', linewidth=1.5, linestyle='--', label=f"Uz_admis = {UZ_LIMIT*1000:.1f} mm  (limite ELS)")
    ax.axhline(uz_crit * 1000, color='#b03030', linewidth=1.5, linestyle=':', label=f"0.1B = {uz_crit*1000:.1f} mm  (critère ELU)")
    ax.axvline(q_ult_SGR / 1000.0, color='#b03030', linewidth=1.2, linestyle=':', alpha=0.6)
    ax.axvline(q_ad_SGR  / 1000.0, color='#2a7f2a', linewidth=1.5, linestyle='--', label=f"q_ad_SGR = {q_ad_SGR:.0f} kPa  (= q_ult/FS)")
    ax.axvline(q_target  / 1000.0, color='#555555', linewidth=1.2, linestyle='-.', alpha=0.7, label=f"q_cible = {q_target:.0f} kPa")
    ax.scatter([q_target / 1000.0], [uz_opt * 1000], color='#e07b39', s=80, zorder=5, label=f"Point de fonctionnement ({q_target:.0f} kPa, {uz_opt*1000:.2f} mm)")

    if els_ok_final and elu_ok_final:
        verdict, tc = "ELS & ELU SATISFAITS", '#2a7f2a'
    elif els_ok_final:
        verdict, tc = "ELS OK — ATTENTION ELU", '#cc7700'
    else:
        verdict, tc = "ELS NON satisfait", '#b03030'

    ax.set_xlabel("Charge appliquée  q  (MPa)", fontsize=11)
    ax.set_ylabel("Tassement  Uz  (mm)",         fontsize=11)
    ax.invert_yaxis()
    ax.set_title(f"Courbe Charge-Tassement SGR — {verdict}\n[B={B:.2f} m  |  FS={FS:.1f}  |  q_cible={q_target:.0f} kPa]", fontsize=11, fontweight='bold', color=tc)
    ax.legend(fontsize=8, loc='lower right')
    ax.grid(True, linestyle='--', alpha=0.45)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    plot_base64 = base64.b64encode(buf.read()).decode('utf-8')

    return {
        'success': True,
        'N_opt': N_opt,
        'h_opt': h_opt,
        'e_opt': e_opt,
        'Lx_opt': Lx_opt,
        'long_couche': long_couche,
        'larg_couche': larg_couche,
        'surf_couche': surf_couche,
        'surface_opt': surface_opt,
        'uz_opt_mm': uz_opt * 1000.0,
        'q_ult_SGR': q_ult_SGR,
        'q_ad_SGR': q_ad_SGR,
        'els_ok': els_ok_final,
        'elu_ok': elu_ok_final,
        'plot_base64': plot_base64
    }

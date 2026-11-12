"""Oppgave 3: Simulere et utbrudd med nedstengning. Referanseløsning."""
from SEIR import SEIR, solve_SEIR, plot_SEIR


# a)
def R_to_beta(R, r_ia=0.1, r_e2=1.25, lmbda_2=0.5, p_a=0.4, mu=0.2):
    return R / ((1 - p_a) * (r_e2 / lmbda_2 + 1 / mu) + p_a * r_ia / mu)


def test_R_to_beta():
    # Med standardverdier er R = 4.7*beta (se oppgaveteksten)
    tol = 1e-10
    assert abs(R_to_beta(4.7) - 1.0) < tol
    assert abs(R_to_beta(1.88) - 0.4) < tol


# b)
class LockdownBeta:
    def __init__(self, t_lock, beta_0, beta_1):
        self.t_lock = t_lock
        self.beta_0 = beta_0
        self.beta_1 = beta_1

    def __call__(self, t):
        if t < self.t_lock:
            return self.beta_0
        else:
            return self.beta_1


if __name__ == "__main__":
    test_R_to_beta()

    beta_0 = R_to_beta(3.2)
    beta_1 = R_to_beta(0.5)

    beta = LockdownBeta(26, beta_0, beta_1)
    model = SEIR(beta=beta)
    t, u = solve_SEIR(model, T=200, N=400, S_0=5.5e6, E2_0=100)
    plot_SEIR(t, u, components=['I', 'Ia'])

    # c)
    print(f"{'t_lock':>8} {'Topp I':>10} {'Respiratorer':>14}")
    for t_lock in [19, 26, 33, 40]:
        model = SEIR(beta=LockdownBeta(t_lock, beta_0, beta_1))
        t, u = solve_SEIR(model, T=200, N=400, S_0=5.5e6, E2_0=100)
        I_peak = max(u[:, 3])
        ventilators = 0.2 * 0.25 * I_peak
        print(f"{t_lock:8d} {I_peak:10.0f} {ventilators:14.0f}")

"""
Kjøring:
  t_lock     Topp I   Respiratorer
      19       2076            104
      26       7750            388
      33      28452           1423
      40      98338           4917

Kommentar: Toppen blir omtrent 3.5-3.7 ganger større for hver uke
nedstengningen utsettes, fordi smitten vokser eksponentielt før tiltakene.
En uke tidligere ville gitt ca. 1/4 av respiratorbehovet ved den virkelige
datoen. En uke senere ville behovet blitt ~1400, dobbelt så mange som de ~700
som finnes, så tidspunktet er svært viktig.
"""

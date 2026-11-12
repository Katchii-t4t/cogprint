"""Oppgave 2: SEIR med tidsavhengig beta. Referanseløsning."""
import sys
import matplotlib.pyplot as plt
from SEIR0 import SEIR0, solve_SEIR


# a)
class SEIR(SEIR0):
    def __init__(self, beta=0.33, r_ia=0.1, r_e2=1.25,
                 lmbda_1=0.33, lmbda_2=0.5, p_a=0.4, mu=0.2):
        if isinstance(beta, (float, int)):      # et tall?
            self.beta_function = lambda t: beta  # pakk inn som funksjon
        elif callable(beta):
            self.beta_function = beta
        else:
            raise TypeError(
                f"beta må være et tall eller en funksjon, fikk {type(beta)}")

        super().__init__(self.beta_function(0), r_ia, r_e2,
                         lmbda_1, lmbda_2, p_a, mu)

    def __call__(self, t, u):
        self.beta = self.beta_function(t)   # oppdater beta for denne t
        return super().__call__(t, u)       # resten gjør basisklassen


# b)
def test_SEIR_beta_const():
    # Samme som test_SEIR0, men med SEIR-klassen
    model = SEIR(beta=0.33)
    computed = model(0, [1, 2, 3, 4, 5, 6])
    infection = 0.33 * 8.25 / 21
    expected = [-infection, infection - 0.33 * 2, 0.33 * 0.6 * 2 - 0.5 * 3,
                0.5 * 3 - 0.2 * 4, 0.33 * 0.4 * 2 - 0.2 * 5, 0.2 * 9]
    tol = 1e-10
    for c, e in zip(computed, expected):
        assert abs(c - e) < tol, f"Fikk {c}, forventet {e}"


def test_SEIR_beta_var():
    # beta(t) = 0.33 - 0.0033 t  ->  beta(0) = 0.33, beta(100) = 0
    beta = lambda t: 0.33 - 0.0033 * t
    model = SEIR(beta=beta)
    u = [1, 2, 3, 4, 5, 6]
    tol = 1e-10

    # t = 0: identisk med konstant-testen
    infection = 0.33 * 8.25 / 21
    dS, dE1 = model(0, u)[:2]
    assert abs(dS - (-infection)) < tol
    assert abs(dE1 - (infection - 0.66)) < tol

    # t = 100: beta = 0, så ingen nye smittede
    dS, dE1 = model(100, u)[:2]
    assert abs(dS - 0) < tol
    assert abs(dE1 - (-0.33 * 2)) < tol


# c)
def plot_SEIR(t, u, components=['S', 'I', 'Ia', 'R']):
    names = ['S', 'E1', 'E2', 'I', 'Ia', 'R']
    for comp in components:
        idx = names.index(comp)
        plt.plot(t, u[:, idx], label=comp)
    plt.xlabel('Time (days)')
    plt.ylabel('Number in each category')
    plt.title('Solution of the SEIR model')
    plt.legend()
    plt.show()


# d)
if __name__ == "__main__":
    test_SEIR_beta_const()
    test_SEIR_beta_var()

    model = SEIR(beta=0.4)
    t, u = solve_SEIR(model, T=200, N=400, S_0=5.5e6, E2_0=100)

    I_peak = max(u[:, 3])
    hospital = 0.2 * I_peak
    ventilators = 0.25 * hospital
    print(f"Topp i I: {I_peak:.0f} personer")
    print(f"Sykehus (20 %): {hospital:.0f}, respirator (25 % av dem): "
          f"{ventilators:.0f}")

    plot_SEIR(t, u)

"""
Kjøring:
Topp i I: 258543 personer
Sykehus (20 %): 51709, respirator (25 % av dem): 12927

Kommentar: Uten tiltak trengs ca. 12 900 respiratorer på det verste,
altså omtrent 18 ganger flere enn de ~700 som finnes i Norge.
"""

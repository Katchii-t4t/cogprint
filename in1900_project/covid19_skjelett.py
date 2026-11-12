"""
Oppgave 5: SKJELETT med hint. Lagre din versjon som covid19.py.
Mønsteret er det samme som i SEIR (Oppgave 2): la basisklassen gjøre jobben.
"""
from SEIR import SEIR, solve_SEIR, plot_SEIR
from lockdown import Beta


class SEIRimport(SEIR):
    def __init__(self, beta=0.33, r_ia=0.1, r_e2=1.25,
                 lmbda_1=0.33, lmbda_2=0.5, p_a=0.4, mu=0.2, sigma=10):
        # TODO: lagre sigma, og send resten videre med super().__init__(...)
        pass

    def __call__(self, t, u):
        # TODO: hent den deriverte fra super().__call__(t, u),
        #       legg til sigma på E2-komponenten (indeks 2), og returner.
        pass


def test_SEIRimport():
    # TODO: lag SEIR(beta=...) og SEIRimport(beta=..., sigma=...) med samme
    #       beta, kall begge med samme t, u. Alle komponenter skal være like
    #       bortsett fra indeks 2, der forskjellen skal være nøyaktig sigma.
    pass


if __name__ == "__main__":
    test_SEIRimport()
    beta = Beta('r_values.txt')
    model = SEIRimport(beta=beta, sigma=10)
    t, u = solve_SEIR(model, T=600, N=600, S_0=5.5e6, E2_0=100)
    plot_SEIR(t, u, components=['I', 'Ia'])

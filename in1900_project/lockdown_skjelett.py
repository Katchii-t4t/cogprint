"""
Oppgave 4: SKJELETT med hint, ikke en ferdig løsning.
Lagre din versjon som lockdown.py. Fyll inn der det står TODO.
"""
from datetime import date, timedelta
import numpy as np
import matplotlib.pyplot as plt
from outbreak import R_to_beta


class Beta:
    def __init__(self, filename):
        self.t0 = date(2020, 2, 15)      # t = 0 i modellen
        self.start_days = []             # startdag for hvert intervall (int)
        self.betas = []                  # beta-verdien i hvert intervall
        self.read_file(filename)

    def str2date(self, date_str):
        day, month, year = (int(n) for n in date_str.split('.'))
        return date(year, month, day)

    def read_file(self, filename):
        with open(filename) as infile:
            # TODO: hopp over overskriftslinjen(e) hvis fila har det
            for line in infile:
                words = line.split()
                # TODO: se på fila og finn ut hvilke ord som er
                #       startdato og R-verdi. Siste linje har ingen sluttdato,
                #       så startdato = words[0] og R = words[-1] er ofte trygt.
                # start = self.str2date(...)
                # R = float(...)
                # self.start_days.append((start - self.t0).days)
                # self.betas.append(R_to_beta(R))
                pass

    def __call__(self, t):
        # Hint fra oppgaven: gå gjennom begge listene med zip, og ta vare
        # på beta for det siste intervallet som har startet (start <= t).
        value = self.betas[0]
        # TODO: for start, b in zip(...):
        return value

    def plot(self, T):
        t = np.linspace(0, T, 1000)
        # __call__ har if-tester, så send ikke hele arrayen inn på én gang:
        beta_values = [self(ti) for ti in t]   # eller np.vectorize(self)(t)
        plt.plot(t, beta_values)
        plt.xlabel('Time (days)')
        plt.ylabel(r'$\beta$')
        plt.title(r'The time-varying $\beta$')
        plt.show()


def test_Beta():
    beta = Beta('r_values.txt')
    # TODO: finn dagen d der første intervall slutter (andre intervall
    #       begynner) i fila, og regn ut forventede beta-er med R_to_beta.
    # d = ...
    # assert abs(beta(d - 1) - R_to_beta(R_første)) < 1e-10
    # assert abs(beta(d) - R_to_beta(R_andre)) < 1e-10


if __name__ == "__main__":
    from SEIR import SEIR, solve_SEIR, plot_SEIR
    test_Beta()
    beta = Beta('r_values.txt')
    beta.plot(600)
    model = SEIR(beta)
    t, u = solve_SEIR(model, T=600, N=600, S_0=5.5e6, E2_0=100)
    plot_SEIR(t, u, components=['I', 'Ia'])

"""
TODO: svar på spørsmålet. Hint: hva skjer med antall smittede etter første
bølge, og kan R > 1 alene starte en ny bølge hvis nesten ingen er smittet?
(Oppgave 5 gir svaret.)
"""

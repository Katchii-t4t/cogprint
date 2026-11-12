"""Oppgave 1: SEEIIR-modellen (kalt SEIR0). Referanseløsning."""
import numpy as np
import matplotlib.pyplot as plt
from ODESolver import RungeKutta4


# a) Klassen SEEIIR fra boka (s. 93), bare omdøpt til SEIR0
class SEIR0:
    def __init__(self, beta=0.33, r_ia=0.1, r_e2=1.25,
                 lmbda_1=0.33, lmbda_2=0.5, p_a=0.4, mu=0.2):
        self.beta = beta
        self.r_ia = r_ia
        self.r_e2 = r_e2
        self.lmbda_1 = lmbda_1
        self.lmbda_2 = lmbda_2
        self.p_a = p_a
        self.mu = mu

    def __call__(self, t, u):
        beta = self.beta
        r_ia = self.r_ia
        r_e2 = self.r_e2
        lmbda_1 = self.lmbda_1
        lmbda_2 = self.lmbda_2
        p_a = self.p_a
        mu = self.mu

        S, E1, E2, I, Ia, R = u
        N = sum(u)
        dS = -beta * S * I / N - r_ia * beta * S * Ia / N \
             - r_e2 * beta * S * E2 / N
        dE1 = beta * S * I / N + r_ia * beta * S * Ia / N \
              + r_e2 * beta * S * E2 / N - lmbda_1 * E1
        dE2 = lmbda_1 * (1 - p_a) * E1 - lmbda_2 * E2
        dI = lmbda_2 * E2 - mu * I
        dIa = lmbda_1 * p_a * E1 - mu * Ia
        dR = mu * (I + Ia)
        return [dS, dE1, dE2, dI, dIa, dR]


def test_SEIR0():
    # Standardparametre, t=0, u=[1,2,3,4,5,6]  ->  N = 21
    # Felles infeksjonsledd: beta*S*(I + r_ia*Ia + r_e2*E2)/N
    #   = 0.33*1*(4 + 0.1*5 + 1.25*3)/21 = 0.33*8.25/21 = 0.12964285714...
    model = SEIR0()
    computed = model(0, [1, 2, 3, 4, 5, 6])
    infection = 0.33 * 8.25 / 21
    expected = [
        -infection,                     # dS
        infection - 0.33 * 2,           # dE1
        0.33 * 0.6 * 2 - 0.5 * 3,       # dE2
        0.5 * 3 - 0.2 * 4,              # dI
        0.33 * 0.4 * 2 - 0.2 * 5,       # dIa
        0.2 * (4 + 5),                  # dR
    ]
    tol = 1e-10
    for c, e in zip(computed, expected):
        assert abs(c - e) < tol, f"Fikk {c}, forventet {e}"


# b)
def solve_SEIR(model, T, N, S_0, E2_0):
    solver = RungeKutta4(model)
    solver.set_initial_condition([S_0, 0, E2_0, 0, 0, 0])
    t, u = solver.solve((0, T), N)
    return t, u


def test_solve_SEIR():
    S_0, E2_0 = 1000, 10
    t, u = solve_SEIR(SEIR0(), T=100, N=200, S_0=S_0, E2_0=E2_0)
    total0 = S_0 + E2_0
    tol = 1e-8
    for i in range(len(t)):          # sjekker hvert tidssteg (fotnote 1)
        assert abs(sum(u[i]) - total0) < tol, \
            f"Antall personer endret seg ved t={t[i]}: {sum(u[i])}"


# c)
def plot_SEIR(t, u):
    S, E1, E2, I, Ia, R = u.T     # u har form (N+1, 6); transponer
    plt.plot(t, S, label='S')
    plt.plot(t, I, label='I')
    plt.plot(t, Ia, label='Ia')
    plt.plot(t, R, label='R')
    plt.xlabel('Time (days)')
    plt.ylabel('Number in each category')
    plt.title('Solution of the SEIR model')
    plt.legend()
    plt.show()


# d)
if __name__ == "__main__":
    test_SEIR0()
    test_solve_SEIR()
    model = SEIR0(beta=0.4)
    t, u = solve_SEIR(model, T=200, N=400, S_0=5.5e6, E2_0=100)
    plot_SEIR(t, u)

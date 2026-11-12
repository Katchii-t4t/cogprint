"""
Minimal kopi av ODESolver-hierarkiet fra IN1900 / "Solving ODEs in Python".
NB: Prosjektet krever at du bruker versjonen fra kursets GitHub-lenke.
Bytt ut denne fila med den offisielle hvis grensesnittet er forskjellig
(spesielt signaturen til solve()).
"""
import numpy as np


class ODESolver:
    def __init__(self, f):
        self.model = f
        self.f = lambda t, u: np.asarray(f(t, u), float)

    def set_initial_condition(self, U0):
        if isinstance(U0, (float, int)):
            self.neq = 1
            U0 = float(U0)
        else:
            U0 = np.asarray(U0)
            self.neq = U0.size
        self.U0 = U0

    def solve(self, t_span, N):
        t0, T = t_span
        self.dt = (T - t0) / N
        self.t = np.zeros(N + 1)
        if self.neq == 1:
            self.u = np.zeros(N + 1)
        else:
            self.u = np.zeros((N + 1, self.neq))

        self.t[0] = t0
        self.u[0] = self.U0

        for n in range(N):
            self.n = n
            self.t[n + 1] = self.t[n] + self.dt
            self.u[n + 1] = self.advance()
        return self.t, self.u

    def advance(self):
        raise NotImplementedError


class ForwardEuler(ODESolver):
    def advance(self):
        u, f, n, t, dt = self.u, self.f, self.n, self.t, self.dt
        return u[n] + dt * f(t[n], u[n])


class RungeKutta4(ODESolver):
    def advance(self):
        u, f, n, t, dt = self.u, self.f, self.n, self.t, self.dt
        dt2 = dt / 2
        k1 = f(t[n], u[n])
        k2 = f(t[n] + dt2, u[n] + dt2 * k1)
        k3 = f(t[n] + dt2, u[n] + dt2 * k2)
        k4 = f(t[n] + dt, u[n] + dt * k3)
        return u[n] + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)

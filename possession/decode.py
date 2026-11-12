"""Décodeur Viterbi : la suite d'états H / A / D la plus cohérente sur une mi-temps.

Chaque image rapporte le score de l'état choisi, chaque changement d'état coûte `switch_cost`.
Le décodeur trouve la suite qui maximise le total. Résultat : des blocs propres, sans clignotement,
ce que le spellF1 récompense.
"""

import numpy as np


def viterbi(scores, switch_cost):
    """Tableau (N,) d'états pour un tableau (N, K) de scores."""
    n, k = scores.shape
    rows = scores.tolist()
    back = np.zeros((n, k), dtype=np.int8)
    best = list(rows[0])

    for t in range(1, n):
        top = max(range(k), key=best.__getitem__)
        jump = best[top] - switch_cost
        row = rows[t]
        pointers = back[t]
        new = [0.0] * k
        for state in range(k):
            if best[state] >= jump:          # rester est au moins aussi bon : on reste
                pointers[state] = state
                new[state] = best[state] + row[state]
            else:
                pointers[state] = top
                new[state] = jump + row[state]
        best = new

    path = np.zeros(n, dtype=np.int8)
    path[-1] = max(range(k), key=best.__getitem__)
    for t in range(n - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def place_switches(path, scores, team_placement=1.0, dead_state=2):
    """Place chaque changement dans le trou sans avis qui sépare deux blocs.

    Entre deux blocs il y a souvent des images sans avis (passe, ballon invisible), et le total du
    décodeur est le même où que l'on coupe dans ce trou. Le trou va de la dernière image qui
    préfère l'ancien état à la première qui préfère le nouveau.

    Un changement qui touche au jeu arrêté est placé à la fin du trou : l'arrêt commence à son
    premier indice, la possession reprend au premier contrôle. Un changement d'équipe à équipe est
    placé à la fraction `team_placement` du trou : 1.0 = à la fin (le ballon reste à l'ancienne
    équipe jusqu'au contrôle adverse), 0.5 = au milieu.
    """
    out = path.copy()
    changes = np.flatnonzero(path[1:] != path[:-1]) + 1
    lows = np.concatenate(([0], changes))
    highs = np.concatenate((changes, [len(path)]))
    for index, start in enumerate(changes):
        old, new = path[start - 1], path[start]
        late = start
        while late < highs[index + 1] - 1 and scores[late, new] <= scores[late, old]:
            late += 1
        cut = late
        if old != dead_state and new != dead_state and team_placement < 1.0:
            early = start
            while early > lows[index] + 1 and scores[early - 1, old] <= scores[early - 1, new]:
                early -= 1
            cut = early + int(round((late - early) * team_placement))
        out[start:cut] = old
        out[cut:start] = new
    return out


def decode(scores, switch_cost, team_placement=1.0):
    return place_switches(viterbi(scores, switch_cost), scores, team_placement)

"""Indices par image : pour chaque image, un score pour H, pour A et pour D.

Un score nul partout veut dire "pas d'avis" : ballon invisible, ballon en l'air loin de tout
joueur, ou duel. Le décodeur prolonge alors l'état précédent, ce qui est la règle du challenge :
un ballon libre ou disputé reste à la dernière équipe qui l'avait.
"""

import numpy as np

from . import config
from .data import AWAY, HOME

H, A, D = 0, 1, 2


def nearest_distance(ball, players, team, side):
    """Distance (m) du ballon au joueur le plus proche d'une équipe ; inf si aucun n'est vu."""
    delta = players[:, team == side, :] - ball[:, None, :]
    dist = np.sqrt((delta ** 2).sum(axis=2))
    return np.where(np.isnan(dist), np.inf, dist).min(axis=1)


def min_run(mask, length):
    """Garde les suites de True d'au moins `length` images, efface les autres."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    out = np.zeros(len(mask), dtype=bool)
    for start, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        if stop - start >= length:
            out[start:stop] = True
    return out


def ball_out(ball, pitch):
    """Ballon vu en dehors des lignes du terrain."""
    length, width = pitch
    margin = config.OUT_MARGIN_M
    with np.errstate(invalid="ignore"):
        return ((ball[:, 0] < -margin) | (ball[:, 0] > length + margin)
                | (ball[:, 1] < -margin) | (ball[:, 1] > width + margin))


def ball_still(ball):
    """Ballon immobile depuis assez longtemps pour que le jeu soit vraisemblablement arrêté."""
    lag = config.STILL_LAG
    moved = np.full(len(ball), np.inf, dtype=np.float32)
    step = ball[lag:] - ball[:-lag]
    moved[lag:] = np.sqrt((step ** 2).sum(axis=1))
    with np.errstate(invalid="ignore"):
        still = moved < config.STILL_DIST_M       # faux si le ballon manque à un des deux bouts
    return min_run(still, config.STILL_MIN_FRAMES)


def runs(mask):
    """[(début, fin)] des suites de True, fin exclue."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def mean_speed(speed):
    """Vitesse moyenne (m/s) des joueurs suivis, lissée ; inf quand aucun joueur n'est suivi."""
    count = (~np.isnan(speed)).sum(axis=1)
    mean = np.nansum(speed, axis=1) / np.maximum(count, 1)
    kernel = np.ones(config.SPEED_SMOOTH_FRAMES) / config.SPEED_SMOOTH_FRAMES
    return np.where(count > 0, np.convolve(mean, kernel, "same"), np.inf)


def dead_gaps(visible, slow, blocks):
    """Ballon perdu de vue longtemps pendant que les joueurs marchent.

    Dans chaque trou assez long, les images lentes comptent comme un arrêt, ainsi que les
    GAP_LEAD_FRAMES images qui précèdent la première : le ballon sort, le tracking le perd, les
    joueurs ne ralentissent que quelques secondes plus tard. Le reste du trou, où les joueurs
    courent, reste sans avis : le jeu peut très bien continuer sans que le ballon soit vu.
    """
    out = np.zeros(len(visible), dtype=bool)
    for first, last in blocks:
        for start, stop in runs(~visible[first:last + 1]):
            if stop - start < config.GAP_MIN_FRAMES:
                continue
            inside = slow[first + start:first + stop]
            slow_at = np.flatnonzero(inside)
            if len(slow_at):
                lead = max(slow_at[0] - config.GAP_LEAD_FRAMES, 0)
                out[first + start:first + stop] = inside
                out[first + start + lead:first + start + slow_at[0]] = True
    return out


def tag_scores(events, blocks, n_frames):
    """Scores (N, 3) tirés du Smart Tagging : arrêts avant les reprises, équipe après."""
    scores = np.zeros((n_frames, 3), dtype=np.float32)
    set_pieces = [e for e in events if e["code"] == "set pieces"]
    kickoffs = sorted(e["start"] + config.KICKOFF_OFFSET for e in set_pieces
                      if e["type"].startswith("kick off"))

    def add(start, stop, state, weight):
        start, stop = max(start, 0), min(stop, n_frames)
        if stop > start:
            scores[start:stop, state] += weight

    for event in set_pieces:
        if event["type"].startswith("kick off"):
            continue
        restart = event["start"] + config.RESTART_OFFSET
        add(restart - config.TAG_DEAD_BEFORE, restart, D, config.W_TAG_DEAD)
        if event["side"] is not None:
            add(restart, restart + config.TAG_TEAM_AFTER, event["side"], config.W_TAG_TEAM)

    # Phases de jeu : préférence douce pour l'équipe qui attaque, au début de la fenêtre. Plusieurs
    # phases de la même équipe qui se chevauchent ne comptent qu'une fois.
    phase = np.zeros((n_frames, 2), dtype=bool)
    for event in events:
        if event["code"] in config.PHASE_CODES and event["side"] is not None:
            length = int((event["end"] - event["start"]) * config.PHASE_FRACTION)
            phase[max(event["start"], 0):event["start"] + length, event["side"]] = True
    scores[:, :2] += config.W_PHASE * phase

    # Début de chaque mi-temps : arrêt jusqu'au coup d'envoi de la mi-temps, s'il tombe dedans.
    # Seuls les coups d'envoi "(start)" comptent ici ; ceux d'après but sont traités plus bas.
    starts = [e["start"] + config.KICKOFF_OFFSET for e in set_pieces
              if e["type"] == "kick off (start)"]
    for first, last in blocks:
        for kickoff in starts:
            if first < kickoff <= last:
                add(first, kickoff, D, config.W_FORCED_DEAD)

    # Après un but : arrêt jusqu'au coup d'envoi suivant.
    for event in events:
        if event["code"] != "goals":
            continue
        following = [k for k in kickoffs if k > event["start"]]
        if following:
            add(event["start"] + config.GOAL_DELAY, following[0], D, config.W_FORCED_DEAD)
    return scores


def build(tracking, events, blocks):
    """(scores, info) : scores est un tableau (N, 3) pour H, A, D ; info sert au rapport.

    `events` vient de tagging.load(), `blocks` est [(première image, dernière image)] par mi-temps.
    """
    ball, players, team = tracking["ball"], tracking["players"], tracking["team"]
    visible = ~np.isnan(ball[:, 0])

    d_home = nearest_distance(ball, players, team, HOME)
    d_away = nearest_distance(ball, players, team, AWAY)
    with np.errstate(invalid="ignore"):
        home_has = visible & (d_home < config.R_CONTROL_M) \
            & (d_home + config.DUEL_MARGIN_M < d_away)
        away_has = visible & (d_away < config.R_CONTROL_M) \
            & (d_away + config.DUEL_MARGIN_M < d_home)

    out = ball_out(ball, tracking["pitch"])
    still = ball_still(ball)
    speed = mean_speed(tracking["speed"])
    # Ballon visible mais tout le monde est quasiment à l'arrêt, durablement.
    stopped = min_run(visible & (speed < config.STOP_SPEED_MS), config.STOP_MIN_FRAMES)
    dead = out | still | stopped

    # Quand le ballon est mort, la proximité d'un joueur ne dit rien : c'est celui qui va tirer le
    # coup franc ou faire la touche. L'indice d'équipe est donc ignoré sur ces images.
    scores = np.zeros((len(ball), 3), dtype=np.float32)
    scores[home_has & ~dead, H] = config.W_TEAM
    scores[away_has & ~dead, A] = config.W_TEAM
    scores[still, D] = config.W_DEAD_STILL
    scores[out, D] = config.W_DEAD_OUT

    gap = dead_gaps(visible, speed < config.SLOW_SPEED_MS, blocks)
    scores[gap, D] += config.W_DEAD_GAP
    scores[stopped, D] += config.W_DEAD_STOPPED
    scores += tag_scores(events, blocks, len(ball))

    info = {"visible": visible, "home_has": home_has & ~dead, "away_has": away_has & ~dead,
            "out": out, "still": still, "gap": gap, "stopped": stopped}
    return scores, info

"""La commande unique : données du match -> fichier de soumission.

    python -m possession.run                  # écrit evaluation/results/<RUN_NAME>.csv
    python -m possession.run --name essai     # autre nom de fichier

Déterministe : mêmes données, même fichier. N'utilise aucune vérité terrain.
"""

import argparse
import os

import numpy as np

from . import config, emissions, tagging
from .data import GAME, ROOT, load_tracking
from .decode import decode
from games import half_video_blocks  # noqa: E402  (ROOT est ajouté au chemin par .data)

RESULTS_DIR = os.path.join(ROOT, "evaluation", "results")
LETTERS = np.array(["H", "A", "D"])


def predict(tracking, game=GAME):
    """(labels, info) : une lettre par image vidéo, X en dehors des deux mi-temps."""
    blocks = [(first, last) for _, first, last in half_video_blocks(game)]
    scores, info = emissions.build(tracking, tagging.load(game), blocks)
    labels = np.full(len(scores), "X", dtype="<U1")
    for first, last in blocks:
        states = decode(scores[first:last + 1], config.SWITCH_COST, config.SWITCH_PLACEMENT)
        labels[first:last + 1] = LETTERS[states]
    return labels, info


def write_submission(path, labels):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w", newline="\n") as handle:
        handle.write("frame,label\n")
        handle.writelines("{},{}\n".format(frame, label) for frame, label in enumerate(labels))
    return path


def report(labels, info, game=GAME):
    """Chiffres de bon sens : parts de chaque lettre, nombre et durée des possessions."""
    graded = np.zeros(len(labels), dtype=bool)
    n_poss, poss_frames = 0, 0
    for _, first, last in half_video_blocks(game):
        graded[first:last + 1] = True
        half = labels[first:last + 1]
        starts = np.concatenate(([0], np.flatnonzero(half[1:] != half[:-1]) + 1))
        stops = np.concatenate((starts[1:], [len(half)]))
        team = np.isin(half[starts], ("H", "A"))
        n_poss += int(team.sum())
        poss_frames += int((stops - starts)[team].sum())

    n = int(graded.sum())
    print("images notées : {}".format(n))
    for name, key in (("ballon visible", "visible"), ("indice domicile", "home_has"),
                      ("indice extérieur", "away_has"), ("ballon hors terrain", "out"),
                      ("ballon immobile", "still"),
                      ("ballon perdu, lent", "gap"),
                      ("tout le monde arrêté", "stopped"),
                      ("dernier frappeur", "kicker")):
        print("  {:<20} {:5.1f} %".format(name, 100.0 * info[key][graded].sum() / n))
    print("réponses :")
    for letter in LETTERS:
        print("  {}  {:5.1f} %".format(letter, 100.0 * np.sum(labels[graded] == letter) / n))
    mean = poss_frames / float(n_poss * config.FPS) if n_poss else 0.0
    print("possessions : {}   durée moyenne : {:.1f} s".format(n_poss, mean))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default=config.RUN_NAME, help="nom du fichier, sans .csv")
    parser.add_argument("--out", default=RESULTS_DIR, help="dossier de sortie")
    args = parser.parse_args()

    tracking = load_tracking()
    labels, info = predict(tracking)
    path = write_submission(os.path.join(args.out, "{}.csv".format(args.name)), labels)
    report(labels, info)
    print("\nécrit : {}".format(os.path.relpath(path, ROOT)))
    print("vérifier : python evaluation/validate_submission.py {}".format(
        os.path.relpath(path, ROOT)))

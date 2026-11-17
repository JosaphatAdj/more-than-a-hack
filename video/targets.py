"""Les images où la vidéo peut changer quelque chose.

    python -m video.targets           # écrit data/cache/video_targets.npy

Sur les ~65 000 images notées sans ballon, nos règles classent déjà la grande majorité en jeu
arrêté (joueurs lents, ballon sorti, coups de pied arrêtés). Il ne reste qu'environ 9 000 images
sans aucun avis : ce sont les seules où une position de ballon retrouvée dans la vidéo peut
modifier le résultat. Les traiter seules rend la détection faisable sans GPU.
"""

import os

import numpy as np

from . import common
from possession import emissions, tagging


def main():
    tracking = common.load_tracking()
    blocks = [(first, last) for _, first, last in common.half_video_blocks(common.GAME)]
    scores, info = emissions.build(tracking, tagging.load(), blocks)
    graded = common.graded_mask(len(scores))
    targets = np.flatnonzero(graded & ~info["visible"] & ~(scores > 0).any(axis=1))
    path = os.path.join(common.ensure_dir(common.CACHE_DIR), "video_targets.npy")
    np.save(path, targets)
    print("{} images cibles écrites dans {}".format(len(targets), path))


if __name__ == '__main__':
    main()

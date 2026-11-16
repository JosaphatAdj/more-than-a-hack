"""Étape 2 (si le modèle de base ne suffit pas) — fabriquer un jeu d'entraînement sans annotation.

    python -m video.make_dataset                # environ 6000 images, quelques minutes
    python -m video.make_dataset --frames 3000

Aucun humain ne décide d'une étiquette : sur les images où le tracking voit le ballon, sa position
de terrain est convertie en pixel par l'homographie, ce qui donne le rectangle du ballon. C'est le
cas "pseudo-étiquettes produites par un algorithme" que RULES.md autorise sur le match fourni.

Ce qui est écrit dans data/cache/yolo_ball/ (jamais dans le dépôt, data/ est ignoré par git) :
  images/train, images/val   découpes de 320x320 px contenant le ballon, plus des découpes sans
  labels/train, labels/val   une ligne "0 xc yc w h" par ballon, fichier vide s'il n'y en a pas
  data.yaml                  la description du jeu pour Ultralytics

Choix
-----
- Seules les images où le ballon va à moins de MAX_SPEED_MS sont gardées : la trajectoire du
  tracking est lissée, et sur un ballon rapide sa position peut être décalée de plusieurs pixels.
- Validation : une minute sur dix, entière, pour que des images voisines presque identiques ne
  se retrouvent pas des deux côtés.
- Une image sur trois fournit aussi une découpe sans ballon, pour apprendre au modèle à ne pas
  prendre une tête ou un point de penalty pour le ballon.
"""

import argparse
import os
import shutil

import numpy as np

from . import common

BALL_DIAMETER_M = 0.22
# Le rectangle est bien plus large que le ballon (6 px), et c'est voulu. Mesuré sur la vidéo : un
# petit objet clair se trouve à moins de 3 px de la position du tracking sur 45 % des images
# seulement, à moins de 10 px sur 80 % (témoin à côté : 17 %). Le tracking place donc le ballon à
# quelques pixels près, pas au pixel près. Un rectangle de 24 px contient le ballon malgré ce
# décalage ; la précision perdue, moins d'un mètre sur le terrain, ne gêne pas nos règles.
BOX_PX = 24.0
MAX_SPEED_MS = 10.0
EDGE_PX = 30              # le ballon est au moins à cette distance du bord de la découpe
NEGATIVE_EVERY = 3
VAL_BLOCK = 1500          # une minute
VAL_EVERY = 10


def is_validation(frames):
    """Vrai pour les images des minutes réservées à la validation."""
    return (np.asarray(frames) // VAL_BLOCK) % VAL_EVERY == VAL_EVERY - 1


def ball_speed(ball, fps=25, lag=5):
    speed = np.full(len(ball), np.inf)
    step = ball[lag:].astype(np.float64) - ball[:-lag].astype(np.float64)
    speed[lag:] = np.sqrt((step ** 2).sum(axis=1)) * fps / lag
    return np.where(np.isnan(speed), np.inf, speed)


def choose_frames(tracking, uv, valid, count, rng):
    n = len(uv)
    ok = common.graded_mask(n) & valid[:n] & ~np.isnan(uv[:, 0])
    ok &= (uv[:, 0] > 20) & (uv[:, 0] < common.FRAME_W - 20)
    ok &= (uv[:, 1] > 20) & (uv[:, 1] < common.FRAME_H - 20)
    ok &= ball_speed(tracking["ball"]) < MAX_SPEED_MS
    candidates = np.flatnonzero(ok)
    picked = rng.choice(candidates, size=min(count, len(candidates)), replace=False)
    return np.sort(picked)


def crop_origin(u, v, rng):
    """Coin d'une découpe carrée de TILE pixels qui contient (u, v), à position aléatoire dans la découpe."""
    tile = common.TILE
    x = int(round(u - rng.uniform(EDGE_PX, tile - EDGE_PX)))
    y = int(round(v - rng.uniform(EDGE_PX, tile - EDGE_PX)))
    return (min(max(x, 0), common.FRAME_W - tile), min(max(y, 0), common.FRAME_H - tile))


def empty_origin(u, v, rng):
    """Coin d'une découpe qui ne contient pas le ballon, ou None si on n'en trouve pas."""
    tile = common.TILE
    for _ in range(20):
        x = int(rng.integers(0, common.FRAME_W - tile + 1))
        y = int(rng.integers(0, common.FRAME_H - tile + 1))
        if not (x - 30 < u < x + tile + 30 and y - 30 < v < y + tile + 30):
            return x, y
    return None


def main():
    import cv2

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, default=6000, help="nombre d'images avec ballon")
    args = parser.parse_args()

    rng = np.random.default_rng(common.SEED)
    common.check_video()
    tracking = common.load_tracking()
    matrices, valid = common.load_homography()
    uv = common.ball_pixels(tracking, matrices, valid)
    frames = choose_frames(tracking, uv, valid, args.frames, rng)
    pitch = tracking["pitch"]

    # On repart d'un dossier vide : les exemples d'un essai précédent ne doivent pas se mélanger.
    if os.path.isdir(common.DATASET_DIR):
        shutil.rmtree(common.DATASET_DIR)
    for kind in ("images", "labels"):
        for split in ("train", "val"):
            common.ensure_dir(os.path.join(common.DATASET_DIR, kind, split))

    counts = {"train": 0, "val": 0, "vides": 0}
    sizes = []
    for done, (index, frame) in enumerate(common.read_frames(frames), 1):
        u, v = uv[index]
        split = "val" if is_validation(index) else "train"
        box = max(BALL_DIAMETER_M / common.metres_per_pixel(matrices[index], u, v, pitch) + 18.0,
                  BOX_PX)
        sizes.append(box)

        x, y = crop_origin(u, v, rng)
        name = "f{:06d}".format(index)
        cv2.imwrite(os.path.join(common.DATASET_DIR, "images", split, name + ".jpg"),
                    frame[y:y + common.TILE, x:x + common.TILE],
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
        with open(os.path.join(common.DATASET_DIR, "labels", split, name + ".txt"), "w") as out:
            out.write("0 {:.6f} {:.6f} {:.6f} {:.6f}\n".format(
                (u - x) / common.TILE, (v - y) / common.TILE,
                box / common.TILE, box / common.TILE))
        counts[split] += 1

        if done % NEGATIVE_EVERY == 0:
            origin = empty_origin(u, v, rng)
            if origin is not None:
                x, y = origin
                cv2.imwrite(os.path.join(common.DATASET_DIR, "images", split, name + "_n.jpg"),
                            frame[y:y + common.TILE, x:x + common.TILE],
                            [cv2.IMWRITE_JPEG_QUALITY, 95])
                open(os.path.join(common.DATASET_DIR, "labels", split, name + "_n.txt"),
                     "w").close()
                counts["vides"] += 1
        if done % 500 == 0:
            print("  {} / {}".format(done, len(frames)))

    with open(os.path.join(common.DATASET_DIR, "data.yaml"), "w") as out:
        out.write("path: {}\ntrain: images/train\nval: images/val\nnames:\n  0: ball\n".format(
            common.DATASET_DIR.replace("\\", "/")))

    print("\nécrit dans {}".format(common.DATASET_DIR))
    print("  entraînement : {} images avec ballon, validation : {}, découpes vides : {}".format(
        counts["train"], counts["val"], counts["vides"]))
    if sizes:
        print("  côté du rectangle du ballon : médiane {:.0f} px (min {:.0f}, max {:.0f})".format(
            np.median(sizes), np.min(sizes), np.max(sizes)))
    print("suite : python -m video.train")


if __name__ == '__main__':
    main()

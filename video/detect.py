"""Étape 4 — détecter le ballon sur les images où le tracking l'a perdu.

    python -m video.detect                # les ~65 000 images notées sans ballon
    python -m video.detect --resume       # reprendre après une interruption
    python -m video.detect --step 2       # une image sur deux, deux fois plus rapide

Écrit data/cache/ball_video.csv, une ligne par candidat, au plus TOP_K par image :

    frame,rank,u,v,conf,x_m,y_m

u, v sont en pixels ; x_m, y_m en mètres sur le terrain, en supposant le ballon au sol (un ballon
en l'air est donc placé trop loin de la caméra). rank 0 est le candidat le plus confiant.

Ce fichier est une donnée dérivée du match : il reste dans data/cache/ et ne va pas dans le dépôt.
C'est lui qu'il faut rapporter sur la machine où tourne possession/.
"""

import argparse
import os

import numpy as np

from . import common

TOP_K = 3
MIN_CONF = 0.05
FRAMES_PER_CALL = 4


def frames_to_process(tracking, valid, step, every_graded):
    n = len(tracking["ball"])
    wanted = common.graded_mask(n) & valid[:n]
    if not every_graded:
        wanted &= np.isnan(tracking["ball"][:, 0])
    return np.flatnonzero(wanted)[::step]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--weights", default=None, help="poids à utiliser")
    parser.add_argument("--step", type=int, default=1, help="traiter une image sur STEP")
    parser.add_argument("--all", action="store_true",
                        help="toutes les images notées, pas seulement celles sans ballon")
    parser.add_argument("--resume", action="store_true", help="continuer un fichier existant")
    parser.add_argument("--everywhere", action="store_true",
                        help="analyser toute l'image, pas seulement près des joueurs")
    parser.add_argument("--device", default="0")
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--out", default=common.DETECTIONS_PATH)
    parser.add_argument("--targets", default=None,
                        help="fichier .npy des images à traiter (sinon : toutes les images sans "
                             "ballon). Voir python -m video.targets")
    args = parser.parse_args()

    device = args.device if args.device == "cpu" else int(args.device)
    detector = common.make_detector(args.weights, MIN_CONF, args.batch, device)

    common.check_video()
    tracking = common.load_tracking()
    matrices, valid = common.load_homography()
    if args.targets:
        frames = np.load(args.targets)[::args.step]
    else:
        frames = frames_to_process(tracking, valid, args.step, args.all)
    pitch = tracking["pitch"]

    common.ensure_dir(os.path.dirname(args.out))
    last_done = -1
    if args.resume and os.path.isfile(args.out):
        with open(args.out) as handle:
            for line in handle:
                head = line.split(",", 1)[0]
                if head.isdigit():
                    last_done = max(last_done, int(head))
        # La dernière image écrite peut être incomplète : on la refait.
        frames = frames[frames >= last_done]
        lines = [line for line in open(args.out)
                 if not line.split(",", 1)[0].isdigit() or int(line.split(",", 1)[0]) < last_done]
        with open(args.out, "w", newline="\n") as handle:
            handle.writelines(lines)
        mode = "a"
        print("reprise à l'image {}".format(last_done))
    else:
        mode = "w"
    print("{} images à traiter".format(len(frames)))

    with_ball = 0
    done = 0
    with open(args.out, mode, newline="\n") as out:
        if mode == "w":
            out.write("frame,rank,u,v,conf,x_m,y_m\n")
        buffer_idx, buffer_img = [], []

        def flush():
            count = 0
            results = detector.detect(buffer_img, None if args.everywhere else [
                common.player_tiles(matrices[i], tracking["players"][i], pitch, detector.origins)
                for i in buffer_idx])
            for index, detections in zip(buffer_idx, results):
                for rank, (u, v, conf, _, _) in enumerate(detections[:TOP_K]):
                    x, y = common.pixel_to_pitch(matrices[index], u, v, pitch)
                    out.write("{},{},{:.1f},{:.1f},{:.3f},{:.2f},{:.2f}\n".format(
                        index, rank, u, v, conf, x, y))
                count += bool(detections)
            out.flush()
            del buffer_idx[:], buffer_img[:]
            return count

        for index, frame in common.read_frames(frames):
            buffer_idx.append(index)
            buffer_img.append(frame)
            if len(buffer_idx) == FRAMES_PER_CALL:
                with_ball += flush()
                done += FRAMES_PER_CALL
                if done % 2000 == 0:
                    print("  {} / {}  ({:.0f} % avec au moins un candidat)".format(
                        done, len(frames), 100.0 * with_ball / done))
        if buffer_idx:
            done += len(buffer_idx)
            with_ball += flush()

    print("\nterminé : {} images, {:.0f} % avec au moins un candidat".format(
        done, 100.0 * with_ball / max(done, 1)))
    print("fichier : {}".format(args.out))


if __name__ == '__main__':
    main()

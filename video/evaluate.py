"""Étape 1 — le détecteur retrouve-t-il le ballon ? Test sans vérité terrain.

    python -m video.evaluate                 # modèle affiné s'il existe, sinon modèle de base
    python -m video.evaluate --base          # force le modèle de base
    python -m video.evaluate --frames 300    # test plus court

On prend des images où le tracking voit le ballon, on convertit sa position en pixel avec
l'homographie, et on regarde si le détecteur trouve quelque chose au même endroit. Le détecteur
ne reçoit aucune information sur la position attendue.

Lecture du résultat
-------------------
- "trouvé"   : une des détections est à moins de RADIUS_PX pixels du ballon du tracking.
- "1er choix": la détection la plus confiante est la bonne. C'est le chiffre qui compte, car dans
               les trous du tracking on n'aura rien pour choisir entre plusieurs candidats.
- "fausses"  : détections ailleurs dans l'image, en moyenne par image.

Repère : un "1er choix" au-dessus de 70 % rend le détecteur utilisable tel quel ; en dessous de
40 %, il faut l'affiner (video.make_dataset puis video.train) et relancer ce test.

Pour un modèle affiné, le test porte sur les minutes réservées à la validation, que
l'entraînement n'a pas vues.
"""

import argparse

import numpy as np

from . import common
from .make_dataset import is_validation

RADIUS_PX = 25.0
THRESHOLDS = (0.05, 0.10, 0.25, 0.50)


def sample_frames(tracking, uv, valid, count, validation_only):
    """Images notées, ballon vu par le tracking et dans le champ, réparties sur le match."""
    n = len(uv)
    ok = common.graded_mask(n) & valid[:n] & ~np.isnan(uv[:, 0])
    ok &= (uv[:, 0] > 20) & (uv[:, 0] < common.FRAME_W - 20)
    ok &= (uv[:, 1] > 20) & (uv[:, 1] < common.FRAME_H - 20)
    if validation_only:
        ok &= is_validation(np.arange(n))
    candidates = np.flatnonzero(ok)
    picks = np.linspace(0, len(candidates) - 1, min(count, len(candidates))).round().astype(int)
    return candidates[np.unique(picks)]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, default=1500, help="nombre d'images testées")
    parser.add_argument("--base", action="store_true", help="forcer le modèle de base")
    parser.add_argument("--weights", default=None, help="poids à tester")
    parser.add_argument("--device", default="0", help="0 pour le GPU, cpu sinon")
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--everywhere", action="store_true",
                        help="analyser toute l'image, pas seulement près des joueurs")
    args = parser.parse_args()

    device = args.device if args.device == "cpu" else int(args.device)
    weights = common.BASE_WEIGHTS if args.base else args.weights
    detector = common.make_detector(weights, min(THRESHOLDS), args.batch, device)
    finetuned = detector.classes is None

    common.check_video()
    tracking = common.load_tracking()
    matrices, valid = common.load_homography()
    uv = common.ball_pixels(tracking, matrices, valid)
    frames = sample_frames(tracking, uv, valid, args.frames, finetuned)
    print("{} images testées{}".format(
        len(frames), " (minutes de validation uniquement)" if finetuned else ""))

    found = {t: 0 for t in THRESHOLDS}
    first = {t: 0 for t in THRESHOLDS}
    false = {t: 0 for t in THRESHOLDS}
    errors_m = []
    done = 0
    pitch = tracking["pitch"]

    buffer_idx, buffer_img = [], []

    def flush():
        results = detector.detect(buffer_img, None if args.everywhere else [
            common.player_tiles(matrices[i], tracking["players"][i], pitch, detector.origins)
            for i in buffer_idx])
        for index, detections in zip(buffer_idx, results):
            u, v = uv[index]
            for threshold in THRESHOLDS:
                kept = [d for d in detections if d[2] >= threshold]
                near = [np.hypot(d[0] - u, d[1] - v) <= RADIUS_PX for d in kept]
                found[threshold] += any(near)
                first[threshold] += bool(near and near[0])
                false[threshold] += len(near) - sum(near)
            if detections and np.hypot(detections[0][0] - u, detections[0][1] - v) <= RADIUS_PX:
                x, y = common.pixel_to_pitch(matrices[index], detections[0][0], detections[0][1],
                                             pitch)
                errors_m.append(np.hypot(x - tracking["ball"][index, 0],
                                         y - tracking["ball"][index, 1]))
        del buffer_idx[:], buffer_img[:]

    for index, frame in common.read_frames(frames):
        buffer_idx.append(index)
        buffer_img.append(frame)
        if len(buffer_idx) == 4:
            flush()
            done += 4
            if done % 200 == 0:
                print("  {} / {}".format(done, len(frames)))
    if buffer_idx:
        done += len(buffer_idx)
        flush()

    print("\nrésultat sur {} images (rayon de {} px)".format(done, int(RADIUS_PX)))
    print("  seuil de confiance   trouvé   1er choix   fausses par image")
    for threshold in THRESHOLDS:
        print("  {:>8.2f}            {:5.1f} %    {:5.1f} %      {:6.2f}".format(
            threshold, 100.0 * found[threshold] / done, 100.0 * first[threshold] / done,
            false[threshold] / float(done)))
    if errors_m:
        print("  écart sur le terrain quand le 1er choix est bon : médiane {:.1f} m, "
              "90e centile {:.1f} m".format(np.median(errors_m), np.percentile(errors_m, 90)))


if __name__ == '__main__':
    main()

"""Étape 3 (si le modèle de base ne suffit pas) — affiner le détecteur sur nos pseudo-étiquettes.

    python -m video.train                 # 30 passes, 30 à 60 minutes sur une RTX 3050
    python -m video.train --epochs 15     # plus court

Part des poids publics yolo11s.pt (COCO) et les spécialise sur une seule classe : le ballon vu par
la caméra tactique. Les poids affinés sont écrits dans
data/cache/yolo_runs/ball/weights/best.pt, que video.evaluate et video.detect prennent ensuite
automatiquement.

Si la carte graphique manque de mémoire ("CUDA out of memory"), relancer avec --batch 8.
"""

import argparse
import os

from . import common


def main():
    from ultralytics import YOLO

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="0")
    args = parser.parse_args()

    data = os.path.join(common.DATASET_DIR, "data.yaml")
    if not os.path.isfile(data):
        raise IOError("jeu d'entraînement absent : lancer d'abord python -m video.make_dataset")

    model = YOLO(common.BASE_WEIGHTS)
    model.train(
        data=data, imgsz=common.IMGSZ, epochs=args.epochs, batch=args.batch,
        device=args.device if args.device == "cpu" else int(args.device),
        project=common.RUNS_DIR, name="ball", exist_ok=True,
        seed=common.SEED, deterministic=True, workers=2,
        # Un ballon de 10 px ne survit ni à un fort changement d'échelle ni au mélange d'images.
        scale=0.2, mosaic=0.0, mixup=0.0, fliplr=0.5,
    )
    print("\npoids affinés : {}".format(common.FINETUNED_WEIGHTS))
    print("suite : python -m video.evaluate   (puis python -m video.detect si le test est bon)")


if __name__ == '__main__':
    main()

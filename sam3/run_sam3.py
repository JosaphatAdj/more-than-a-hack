"""Détection SAM3 « soccer ball » sur les images de la vidéo tactique (GPU CUDA requis).

Prérequis : accepter la licence de facebook/sam3 sur Hugging Face, puis exporter HF_TOKEN
(ou `huggingface-cli login`).

Usage :
    python sam3/run_sam3.py --video tactical.mp4 --frames frames_sam3.npy
    python sam3/run_sam3.py --video tactical.mp4 --frames frames_extra.npy --out sam3_candidats_extra.pkl

--frames : fichier .npy d'indices d'images vidéo (0-indexés) à traiter.
--step   : 2 = une image sur deux (coût divisé par 2).
Sortie   : pickle [(image, boîtes [x0,y0,x1,y1], scores), ...] lu par le notebook.
Reprise  : si --out existe déjà, les images qu'il contient sont ignorées.
"""
import argparse
import os
import pickle

import cv2
import numpy as np
import torch
from PIL import Image
from tqdm.auto import tqdm
from transformers import Sam3Model, Sam3Processor

ap = argparse.ArgumentParser()
ap.add_argument("--video", required=True)
ap.add_argument("--frames", required=True)
ap.add_argument("--out", default="sam3_candidats.pkl")
ap.add_argument("--step", type=int, default=1)
ap.add_argument("--save-every", type=int, default=2000)
a = ap.parse_args()

results = pickle.load(open(a.out, "rb")) if os.path.exists(a.out) else []
done = {r[0] for r in results}
frames = [int(f) for f in np.load(a.frames)[::a.step] if int(f) not in done]
print(f"{len(frames)} images à traiter ({len(done)} déjà faites)")

model = Sam3Model.from_pretrained("facebook/sam3", device_map={"": 0}).eval()
proc = Sam3Processor.from_pretrained("facebook/sam3")
cap, last = cv2.VideoCapture(a.video), -10

for k, f in enumerate(tqdm(frames, unit="img", desc="SAM3")):
    if f != last + 1:
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ok, bgr = cap.read()
    last = f
    assert ok, f"lecture impossible : {f}"
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    with torch.no_grad():                               # prompt « soccer ball », image pleine, seuil 0,2
        inp = proc(images=im, text="soccer ball", return_tensors="pt").to(model.device)
        r = proc.post_process_instance_segmentation(
            model(**inp), threshold=0.2, mask_threshold=0.5,
            target_sizes=inp.get("original_sizes").tolist())[0]
    results.append((f, r["boxes"].float().cpu().numpy().round(1).tolist(),
                    r["scores"].float().cpu().numpy().round(3).tolist()))
    if (k + 1) % a.save_every == 0:
        pickle.dump(sorted(results), open(a.out, "wb"))

pickle.dump(sorted(results), open(a.out, "wb"))
print(f"{len(results)} images -> {a.out}")
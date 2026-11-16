# Ball possession, frame by frame — More than a Hack 2027

Our entry (team Goal Tensor) to [More than a Hack 2027, Phase 1](README_KIT.md): for every frame of
the tactical video of FC Barcelona vs Athletic Club, say whether the home team (`H`) or the away
team (`A`) has the ball, or whether the ball is dead (`D`).

The method is a set of rules on the provided automatic tracking, decoded with a Viterbi pass over
each half. There are two versions in this repository:

| Version | Inputs | Training | Public 5 min (macroF1 / spellF1) |
|---|---|---|---|
| **Numpy pipeline** (`possession/`, `tour5`) | tracking + Smart Tagging | none | see [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) |
| **Final, with SAM3 ball recovery** (notebook) | tracking + tactical video + homography | none | 0.825 / 0.563, 15 possessions (truth: 17) |

The numpy pipeline uses no video, no external data and no ground truth. The final version adds
SAM3 ball detections on the video where the tracking lost the ball (zero-shot, nothing is trained)
and replaces the Smart Tagging by stoppage cues computed from the tracking. Its rules are in
[REGLES_POSSESSION_FINAL.md](REGLES_POSSESSION_FINAL.md); the numpy pipeline's rules are in
[REGLES_POSSESSION.md](REGLES_POSSESSION.md). Both are described in [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md).

The organisers' starter kit is kept unchanged in this repository (`evaluation/`, `starter/`,
`games.py` and the challenge documents); its original README is [README_KIT.md](README_KIT.md).

## Reproduce the numpy pipeline

Requirements: Python 3.14 (developed and verified with 3.14.7 on Windows 11). The pipeline itself
needs only numpy.

1. Put the match data where the kit expects it, keeping the names it arrives with:

   ```
   data/tactical/BAR-ATH_tactical_atd.xml
   data/tactical/BAR-ATH_tactical_atd.txt
   data/tactical/BAR-ATH_tactical_smart_tagging.xml
   ```

   or point `MTAH_DATA_DIR` at the folder that contains `tactical/`. The video, the homography and
   the broadcast files are not used by this version.

2. Install the pinned dependencies:

   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-lock.txt     # Windows
   .venv/bin/python -m pip install -r requirements-lock.txt         # macOS / Linux
   ```

3. Generate the file, then check it with the kit's validator:

   ```bash
   .venv/Scripts/python -m possession.run --name <team_name>
   .venv/Scripts/python evaluation/validate_submission.py evaluation/results/<team_name>.csv
   ```

The run takes about 20 seconds once the tracking has been parsed; the first run parses the 196 MB
tracking file and caches it in `data/cache/` (a minute or two). The output is deterministic: the
same data gives the same file, byte for byte.

Optional: score it on the public 5-minute window with `python evaluation/run_evaluation.py`.

## Reproduce the final version (SAM3)

Needs the tactical video and the homography in addition to the tracking
(`*tactical.mp4`, `*tactical_homography.csv`), plus `requirements-sam3.txt`.

1. **SAM3 candidates.** The notebook `mtah-2027-final.ipynb` reads `sam3_candidats.pkl` (and
   `sam3_candidats_extra.pkl` if present). If you do not have them, compute them (CUDA GPU needed;
   `facebook/sam3` is gated: accept the licence on Hugging Face and `export HF_TOKEN=hf_xxx`):

   ```python
   # in the notebook, after the stoppage cues (STOPS) are computed
   NEED = INSIDE & ~VIS & ~(STOPS > 0)       # in play, no tracking ball, no stoppage
   np.save("frames_sam3.npy", np.flatnonzero(NEED))
   ```

   ```bash
   pip install -r requirements-sam3.txt
   python sam3/run_sam3.py --video tactical.mp4 --frames frames_sam3.npy
   ```

   Prompt "soccer ball", full-resolution frames, score threshold 0.2, all boxes kept. `--step 2`
   processes one frame out of two. The script saves regularly and resumes if `--out` exists.

   The candidates shipped with the submission were computed with an earlier frame selection (a
   dead-ball model and Smart Tagging windows). To process only the frames they miss:

   ```python
   np.save("frames_extra.npy", np.flatnonzero(NEED & ~np.isin(np.arange(T), SAM.index)))
   ```

   ```bash
   python sam3/run_sam3.py --video tactical.mp4 --frames frames_extra.npy --out sam3_candidats_extra.pkl
   ```

2. Run the notebook top to bottom. It tracks the ball (Viterbi + Kalman on the candidates), scores
   the six ablation variants and writes `submission.csv` (header `frame,label`, 199,319 rows).

3. Validate: `python evaluation/validate_submission.py submission.csv`.

Decoding is deterministic; SAM3 scores may differ slightly between GPU types.

## Layout

```
possession/
  config.py      every parameter, with the reason for its value
  data.py        reads the tracking into numpy arrays, with a cache
  tagging.py     reads the Smart Tagging
  emissions.py   per-frame evidence for H / A / D
  decode.py      Viterbi decoder and placement of the transitions
  run.py         the single command: data -> evaluation/results/<name>.csv
sam3/run_sam3.py             SAM3 ball detection on video frames (GPU)
mtah-2027-final.ipynb        final version: stoppage cues, SAM3 tracking, decoder, submission.csv
TECHNICAL_REPORT.md      the technical document
REGLES_POSSESSION.md         rules of the numpy pipeline (French)
REGLES_POSSESSION_FINAL.md   rules of the final version (French)
PLAN.md                  working plan and results log (French)
requirements-lock.txt    pinned dependencies (numpy pipeline)
requirements-sam3.txt    extra dependencies (SAM3 and notebook)
```

## Data

The match data is licensed for the competition only and is not in this repository: `data/` is
gitignored except for its README, and so are all submission files in `evaluation/results/` other
than the kit's four baselines.
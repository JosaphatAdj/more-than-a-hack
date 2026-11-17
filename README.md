# Ball possession, frame by frame — More than a Hack 2027

Our entry (team Goal Tensor) to [More than a Hack 2027, Phase 1](README_KIT.md): for every frame of the tactical
video of FC Barcelona vs Athletic Club, say whether the home team (`H`) or the away team (`A`)
has the ball, or whether the ball is dead (`D`).

The method is a set of rules on the provided automatic tracking and Smart Tagging, decoded with a
Viterbi pass over each half. No video, no external data, no training, no ground truth. It is
described in [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md).

The organisers' starter kit is kept unchanged in this repository (`evaluation/`, `starter/`,
`games.py` and the challenge documents); its original README is [README_KIT.md](README_KIT.md).

## Reproduce the submission

Requirements: Python 3.14 (developed and verified with 3.14.7 on Windows 11). The pipeline itself
needs only numpy.

1. Put the match data where the kit expects it, keeping the names it arrives with:

   ```
   data/tactical/BAR-ATH_tactical_atd.xml
   data/tactical/BAR-ATH_tactical_atd.txt
   data/tactical/BAR-ATH_tactical_smart_tagging.xml
   ```

   or point `MTAH_DATA_DIR` at the folder that contains `tactical/`. The video, the homography and
   the broadcast files are not used.

2. Install the pinned dependencies:

   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-lock.txt     # Windows
   .venv/bin/python -m pip install -r requirements-lock.txt         # macOS / Linux
   ```

3. Generate the file, then check it with the kit's validator:

   ```bash
   .venv/Scripts/python -m possession.run --name goal_tensor --out .
   .venv/Scripts/python evaluation/validate_submission.py goal_tensor.csv
   ```

   This rewrites `goal_tensor.csv`, the submitted file, at the root of the repository.

The run takes about 20 seconds once the tracking has been parsed; the first run parses the 196 MB
tracking file and caches it in `data/cache/` (a minute or two). The output is deterministic: the
same data gives the same file, byte for byte.

Optional: score it on the public 5-minute window with `python evaluation/run_evaluation.py`.

## Layout

```
possession/
  config.py      every parameter, with the reason for its value
  data.py        reads the tracking into numpy arrays, with a cache
  tagging.py     reads the Smart Tagging
  emissions.py   per-frame evidence for H / A / D
  decode.py      Viterbi decoder and placement of the transitions
  run.py         the single command: data -> <name>.csv
goal_tensor.csv          the submitted file (output of the command above)
TECHNICAL_REPORT.md      the technical document
REGLES_POSSESSION.md     the rules in detail (French)
PLAN.md                  working plan and results log (French)
requirements-lock.txt    pinned dependencies
```

## Data

The match data is licensed for the competition only and is not in this repository: `data/` is
gitignored except for its README, and so are all submission files in `evaluation/results/` other
than the kit's four baselines.

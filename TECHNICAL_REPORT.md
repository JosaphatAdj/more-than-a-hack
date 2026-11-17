# Technical report — rule-based possession from automatic tracking

More than a Hack 2027, Phase 1: ball possession, FC Barcelona vs Athletic Club.

## 1. Approach

The ranking metric, `spellF1`, scores possessions as whole objects. Getting the shape of each
possession right matters more than getting individual frames right: one flicker in the middle of a
possession splits it in two and also invents a third, short one. We therefore designed the
system in two stages.

1. **Per-frame evidence.** Rules read the tracking and the Smart Tagging and give each frame a
   score for each of the three states `H`, `A` and `D`. A frame with no score at all has **no
   opinion**: ball not tracked, ball in flight away from every player, or a duel. About half of
   the graded frames are in that case.
2. **Sequence decoding.** A Viterbi decoder picks, for each half separately, the sequence of states
   with the highest total score, paying a fixed cost for every change of state. It produces clean
   segments, carries the current state through frames with no opinion, and uses both past and
   future frames.

We chose rules over a learned model for three reasons:

- there are no labels for this match, and the rules forbid hand labels on it;
- the public 5 minutes (17 possessions) are too small to train or tune on;
- every decision has to be explainable in this document.

We did test a self-trained model (section 6); it did not help.

## 2. Assets

| Asset | Used | How |
|---|---|---|
| Tactical tracking (ATD) | yes | ball and player positions, player speeds, team of each track |
| Smart Tagging | yes | set pieces (restarts, team), goals, kick-offs |
| Homography | no | measured, dropped (section 6) |
| Tactical video | no | not used in this version |
| Broadcast video, tracking and homography | no | not synchronised with the tactical feed; not needed by the method |
| Public 5-minute ground truth | checking only | see section 7 |

**Training data: none.** No labelled data of any kind was used, from this match or any other.
There is no learned component in the submitted pipeline.

**Alignment.** Tracking record `frame_id` is video frame `frame_id − 1`; Smart Tagging seconds × 25
is the video frame. Frames outside the two halves (`games.half_video_blocks`) are written as `X`.

## 3. Possession rules

All parameters live in `possession/config.py`, each with the reason for its value. Distances are in
metres on a 105.3 × 68 m pitch; durations in frames at 25 fps.

### 3.1 Who has the ball (`H` / `A`)

**Close control (weight 1.0).** The ball is tracked, the nearest player is within 2 m of it, and
the nearest opponent is at least 0.5 m further away. Otherwise it is a duel and gives no opinion.
Coverage: 26.5 % of graded frames.

**Last kicker (weight 0.5).** This is the rule that gives an opinion while a pass is travelling.

- **Detecting a kick.** A kick (pass, shot, controlled touch) is a local peak of at least 6 m/s
  in the change of ball velocity, comparing the 12 frames before and after.
  - The window has to be that long because the provided ball trajectory is smoothed: over 3
    frames almost no pass is visible.
- **Attributing it.** The kick goes to the nearest player if they are within 3 m and clearly
  closer than the nearest opponent.
- **Holding it.** Until the next kick, for at most 3 s, the kicker's team scores 0.5 per frame.
  An unattributable kick, a lost ball or any dead-ball cue ends it.

Measured on the whole match, without ground truth:

- 973 kicks, roughly one every 3 s of live play, 79 % of them attributable;
- 89 % agreement with close control when both give an opinion;
- coverage: 25 % of graded frames.

**Set-piece team (weight 0.5).** For the 3 s after a tagged restart whose `Team` tag is filled in,
that team is favoured. Throw-ins are all tagged `N/A`, so they get nothing.

### 3.2 Dead ball (`D`)

On any frame carrying an out-of-pitch, stationary-ball or everyone-stopped cue, close control and
last kicker are ignored. The player next to a dead ball is the one about to restart, which is not
possession.

| Cue | Condition | Weight | Coverage |
|---|---|---|---|
| Ball out | ball tracked more than 0.5 m outside a line | 2.0 | 2.1 % |
| Ball stationary | ball moves less than 0.5 m in 1 s, for at least 2 s | 1.0 | 1.6 % |
| Ball lost, players slow | see below | 0.5 | 34.0 % |
| Everyone stopped | ball tracked, mean player speed below 1 m/s for at least 2 s | 0.5 | 3.7 % |
| Before a tagged restart | the 4 s before the estimated restart | 1.0 | — |
| Before a kick-off | start of each half, and after each tagged goal until the kick-off | 5.0 | — |

**Ball lost, players slow.** This cue applies inside every gap of at least 3 s in the ball track.

- Frames where the mean player speed, smoothed over 1 s, is below 1.5 m/s count as dead.
- So do the 2 s before the first slow frame, because players slow down a little after the ball
  goes out.
- The rest of the gap, where players run, has no opinion: play can go on with the ball unseen.

Why 1.5 m/s: measured on the whole match, players are below it on 82 % of the frames of long gaps,
against 27 % of frames where the ball is tracked. Walking pace is about 1.4 m/s.

**Restart timing.** Smart Tagging set pieces are fixed-length windows (35 s, or 5 s for
kick-offs), not instants. We averaged player speed and ball visibility around the 53 non-kick-off
set-piece tags. That profile places the restart about 5 s after the tag start, and 3.4 s for
kick-offs, which matches the two kick-off frames published in `DATA.md`.

### 3.3 Decoding

**Switch cost: 10.** Close control scores 1 per frame, which gives two behaviours:

- an isolated opponent touch shorter than about 0.8 s cannot pay for a switch and a switch back,
  so it is ignored. This implements "a simple touch without control does not change possession";
- sustained control of about 0.4 s by the other team does switch possession.

The value was chosen on plausibility, not on ground truth. A cost of 25 produced 148 possessions
of 39 s on average over the match. A cost of 10 gives about 10 s, in line with professional
football.

**No-opinion frames** score nothing, so the decoder carries the previous state through them: a
loose or contested ball stays with the last team that had it, as the challenge rules say.

**Placing each transition.** Between two segments there is often a run of no-opinion frames, and
the decoder's total is the same wherever it cuts inside that run.

- **Team to team:** we cut in the middle of the run, the minimum-error choice when nothing else
  is known.
- **To or from dead ball:** we cut at the end of the run. A stoppage starts at its first cue, and
  possession resumes at the first control.

## 4. Handling missing and noisy tracking

The ball is untracked on 41 % of graded frames, players are anonymous track slots, and tracks
drop out.

- **Missing ball.** It is never read as dead ball; that was the main fault of the starter
  baseline. A short gap means no opinion, and the decoder carries the current state through it.
  A long gap is read as a stoppage only on the frames where the players are also slow.
- **Anonymous players.** Every rule is team-level: nearest player per team, mean speed over all
  tracked players. Identity switches between tracks therefore do not matter.
- **Missing players.** Distances use only the players present; a frame with no tracked player
  of a team simply gives that team no evidence.
- **Smoothed ball trajectory.** Kick detection uses half-second velocity windows.

## 5. Results

On the whole match (no ground truth): 31.4 % `H`, 20.2 % `A`, 48.3 % `D`, 334 possessions with a
mean duration of 9.8 s.

On the public 5-minute window, scored with the kit's `run_evaluation.py`:

| Version | spellF1 | macroF1 | Predicted possessions (17 true) |
|---|---|---|---|
| `baseline_smooth50` (published floor) | 0.3256 | 0.6207 | 26 |
| close control + decoder | 0.3871 | 0.5586 | 14 |
| + dead-ball cues + Smart Tagging | 0.4471 | 0.7061 | 17 |
| + refined stoppages, mid-gap transitions | 0.4824 | 0.7670 | 17 |
| **+ last kicker (submitted)** | **0.5436** | **0.7587** | **22** |

17 possessions are too few to rank versions: one possession moves `spellF1` by about 0.05 here.
These figures show that the pipeline is correct; they do not measure its quality on the full
match.

## 6. Tried and dropped

| Idea | Measurement | Decision |
|---|---|---|
| Smart Tagging phases (Build Up, Progression…) as a soft team prior | 80–90 % agreement with close control in the first 40 % of each window; changed 1.1 % of frames, no gain | disabled (`W_PHASE = 0`) |
| "Defending …" tags | exact mirrors of the attacking tags | not used |
| Direction of collective movement | right team 60 % of the time | dropped |
| Camera aim from the homography, as a ball proxy | follows the ball only within 12 m (median) | dropped |
| Direction of camera pan | right team 55–70 % of the time | dropped |
| Self-trained classifier on players only (105 features over ±4 s windows, pseudo-labels from confident rule frames, trained on one half and tested on the other) | 83 % correct with the ball hidden; no `spellF1` gain when used as weak evidence, a loss when used widely, because its smooth features blur transition timing | dropped |

## 7. Limitations

- **Gaps in the ball track.** Inside a long gap where players keep running, the system has no
  information. A change of possession there is placed in the middle of the gap at best.
- **Short stoppages.** Stoppages with the ball still tracked and players moving, such as a quick
  throw-in, are missed: 57 % of dead-ball frames are recovered on the public window.
- **Deflections.** A deflection looks like a kick to the last-kicker rule and can hand possession
  to the deflecting team for up to 3 s. This is probably why we predict 22 possessions for 17 on
  the public window.
- **Goalkeeper holding the ball.** After 2 s this becomes a stationary-ball stoppage, while it is
  live play.
- **Goal tags.** The dead-ball window after a goal starts 2 s after the tag start. If a tag starts
  at the beginning of the attack rather than at the goal, part of a live attack is labelled `D`.
- **Very short possessions.** Possessions shorter than about 0.8 s cannot be produced by
  construction.
- **Use of the public window.** No parameter was optimised on it. However, while designing the
  dead-ball refinements and the mid-gap placement, we compared our transitions with the public
  window's transitions to understand what was going wrong. Every threshold was then set from
  football reasoning or from statistics on the full match.

**With more time:**

- detect the ball in the tactical video to fill the 41 % gap;
- treat a kick as a change of possession only if the kicker's team keeps the ball afterwards;
- check where goal tags start;
- require slow players before calling a stationary ball dead.

## 8. Reproduction

See [README.md](README.md). In short:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-lock.txt
.venv/Scripts/python -m possession.run --name goal_tensor --out .   # writes goal_tensor.csv
```

Inputs are `data/tactical/BAR-ATH_tactical_atd.{xml,txt}` and
`data/tactical/BAR-ATH_tactical_smart_tagging.xml`. The output is deterministic and was checked
byte for byte against the submitted file from a fresh clone.

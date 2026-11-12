"""Lecture du tracking (ATD) en tableaux numpy, avec un cache local.

Format du fichier brut, une ligne par image :

    <frame_id>:<joueur>;<joueur>;...:<ballon>

Chaque groupe est "x,y,vitesse" en coordonnées normalisées 0-1, ou NaN si l'objet n'est pas vu.
frame_id compte à partir de 1, les soumissions à partir de 0 : image vidéo = frame_id - 1.

La lecture prend une minute ou deux ; le résultat est mis en cache dans data/cache/ (ignoré par
git) et relu en une seconde tant que le fichier source n'a pas changé.
"""

import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import DATA_DIR, GAME, GAMES, require, source_frames  # noqa: E402

HOME, AWAY = 0, 1


def team_of_each_track(meta_path):
    """Tableau sur les pistes : 0 si la piste appartient à l'équipe à domicile, 1 sinon.

    La première équipe du fichier est celle à domicile (convention FIFA/EPTS).
    """
    root = ET.parse(meta_path).getroot()
    team_ids = [team.get("id") for team in root.iter("Team")]
    if len(team_ids) != 2:
        raise ValueError("{}: 2 équipes attendues, {} trouvées".format(meta_path, len(team_ids)))
    slots = [player.get("teamId") for player in root.iter("Player")]
    if not slots:
        raise ValueError("{}: aucune entrée Player".format(meta_path))
    return np.array([HOME if team == team_ids[0] else AWAY for team in slots], dtype=np.int8)


def _parse(raw_path, n_frames, n_slots, pitch):
    """(ball, players, speed) en mètres ; NaN là où l'objet n'est pas vu."""
    length, width = pitch
    ball = np.full((n_frames, 2), np.nan, dtype=np.float32)
    players = np.full((n_frames, n_slots, 2), np.nan, dtype=np.float32)
    speed = np.full((n_frames, n_slots), np.nan, dtype=np.float32)

    with open(raw_path) as handle:
        for line in handle:
            parts = line.rstrip("\n").split(":")
            if len(parts) != 3:
                continue
            row = int(parts[0]) - 1
            if not 0 <= row < n_frames:
                continue

            fields = parts[2].split(",")
            if len(fields) >= 2 and fields[0][:1] not in ("N", "n", ""):
                ball[row, 0] = float(fields[0]) * length
                ball[row, 1] = float(fields[1]) * width

            for slot, group in enumerate(parts[1].split(";")[:n_slots]):
                if group[:1] in ("N", "n", ""):
                    continue
                fields = group.split(",")
                players[row, slot, 0] = float(fields[0]) * length
                players[row, slot, 1] = float(fields[1]) * width
                if len(fields) > 2 and fields[2][:1] not in ("N", "n", ""):
                    speed[row, slot] = float(fields[2])
    return ball, players, speed


def load_tracking(game=GAME, data_dir=None, use_cache=True):
    """dict : ball (N,2), players (N,S,2), speed (N,S), team (S,), pitch (longueur, largeur).

    Positions en mètres, origine dans un coin du terrain. La ligne i est l'image vidéo i.
    """
    meta_path, raw_path = require(["atd_meta", "atd_raw"], game, data_dir)
    n_frames = source_frames("tactical", game)
    pitch = GAMES[game]["pitch"]
    team = team_of_each_track(meta_path)

    cache_dir = os.path.join(data_dir or DATA_DIR, "cache")
    cache_path = os.path.join(cache_dir, "{}_tactical_atd.npz".format(game))
    stat = os.stat(raw_path)
    stamp = np.array([stat.st_size, int(stat.st_mtime)], dtype=np.int64)

    if use_cache and os.path.isfile(cache_path):
        with np.load(cache_path) as cached:
            if np.array_equal(cached["stamp"], stamp):
                return {"ball": cached["ball"], "players": cached["players"],
                        "speed": cached["speed"], "team": team, "pitch": pitch}

    print("lecture de {} (une à deux minutes, puis mis en cache) ...".format(
        os.path.basename(raw_path)))
    ball, players, speed = _parse(raw_path, n_frames, len(team), pitch)
    if use_cache:
        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir)
        np.savez(cache_path, ball=ball, players=players, speed=speed, stamp=stamp)
    return {"ball": ball, "players": players, "speed": speed, "team": team, "pitch": pitch}

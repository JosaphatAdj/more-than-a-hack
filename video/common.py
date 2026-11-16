"""Outils communs : chemins, homographie, lecture de la vidéo, tuiles, appel du détecteur.

Conventions
-----------
- L'image vidéo i est la ligne i du tracking, de l'homographie et de la soumission.
- L'homographie envoie les coordonnées de terrain normalisées (0-1) vers les pixels.
- Les positions de terrain sont en mètres, comme dans possession/data.py.
"""

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import DATA_DIR, GAME, GAMES, half_video_blocks, require  # noqa: E402
from possession.data import load_tracking  # noqa: E402,F401

CACHE_DIR = os.path.join(DATA_DIR, "cache")
DATASET_DIR = os.path.join(CACHE_DIR, "yolo_ball")
RUNS_DIR = os.path.join(CACHE_DIR, "yolo_runs")
DETECTIONS_PATH = os.path.join(CACHE_DIR, "ball_video.csv")
FINETUNED_WEIGHTS = os.path.join(RUNS_DIR, "ball", "weights", "best.pt")

# Modèle de base : poids publics Ultralytics entraînés sur COCO, téléchargés au premier appel.
BASE_WEIGHTS = "yolo11s.pt"
COCO_SPORTS_BALL = 32

FRAME_W, FRAME_H = 1920, 1080
# Le ballon ne fait que 4 à 11 pixels de diamètre dans cette vidéo (6 en médiane, d'après
# l'homographie). On découpe donc des tuiles de TILE pixels que le modèle agrandit à IMGSZ :
# le ballon double de taille avant d'être analysé.
TILE = 320
IMGSZ = 640
SEED = 0


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def graded_mask(n_frames, game=GAME):
    """Vrai sur les images des deux mi-temps."""
    mask = np.zeros(n_frames, dtype=bool)
    for _, first, last in half_video_blocks(game):
        mask[first:last + 1] = True
    return mask


# -- homographie ---------------------------------------------------------------------------------

def load_homography(game=GAME):
    """(matrices (N,3,3), valid (N,)) ; les matrices invalides sont NaN."""
    path = require(["homography"], game)[0]
    table = np.genfromtxt(path, delimiter=",", skip_header=1, dtype=np.float64)
    return table[:, 1:10].reshape(-1, 3, 3), table[:, 11] == 1


def pitch_to_pixel(matrix, x_m, y_m, pitch):
    """Position de terrain (m) -> pixel (u, v) pour une matrice 3x3."""
    vec = matrix @ np.array([x_m / pitch[0], y_m / pitch[1], 1.0])
    return vec[0] / vec[2], vec[1] / vec[2]


def pixel_to_pitch(matrix, u, v, pitch):
    """Pixel -> position de terrain (m), en supposant le point au sol."""
    vec = np.linalg.solve(matrix, np.array([u, v, 1.0]))
    return vec[0] / vec[2] * pitch[0], vec[1] / vec[2] * pitch[1]


def ball_pixels(tracking, matrices, valid):
    """Pixel (u, v) du ballon du tracking sur chaque image ; NaN quand il n'est pas vu."""
    ball, pitch = tracking["ball"].astype(np.float64), tracking["pitch"]
    n = len(ball)
    pts = np.stack([ball[:, 0] / pitch[0], ball[:, 1] / pitch[1], np.ones(n)], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        proj = np.einsum("nij,nj->ni", matrices[:n], pts)
        uv = proj[:, :2] / proj[:, 2:3]
    uv[~valid[:n]] = np.nan
    return uv


def metres_per_pixel(matrix, u, v, pitch):
    """Taille au sol d'un pixel autour de (u, v) : sert à dimensionner le rectangle du ballon."""
    x0, y0 = pixel_to_pitch(matrix, u, v, pitch)
    x1, y1 = pixel_to_pitch(matrix, u + 1.0, v, pitch)
    return float(np.hypot(x1 - x0, y1 - y0))


# -- vidéo ---------------------------------------------------------------------------------------

def video_path(game=GAME):
    return require(["video"], game)[0]


def read_frames(wanted, game=GAME):
    """Génère (index, image BGR) pour les index demandés, dans l'ordre croissant.

    Lecture séquentielle : le positionnement direct dans un mp4 n'est pas exact à l'image près,
    et une image de décalage fausserait tout. Les images non demandées sont sautées avec grab(),
    qui ne les décode pas.
    """
    import cv2

    wanted = np.unique(np.asarray(wanted, dtype=np.int64))
    if not len(wanted):
        return
    capture = cv2.VideoCapture(video_path(game))
    if not capture.isOpened():
        raise IOError("impossible d'ouvrir la vidéo : {}".format(video_path(game)))
    try:
        position, cursor = 0, 0
        while cursor < len(wanted):
            target = int(wanted[cursor])
            while position < target:
                if not capture.grab():
                    return
                position += 1
            ok, frame = capture.read()
            if not ok:
                return
            position += 1
            cursor += 1
            yield target, frame
    finally:
        capture.release()


def check_video(game=GAME):
    """Vérifie taille et nombre d'images ; renvoie le nombre d'images annoncé par le fichier."""
    import cv2

    capture = cv2.VideoCapture(video_path(game))
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    expected = GAMES[game]["n_video_frames"]
    print("vidéo : {} images, {}x{} (attendu : {} images, {}x{})".format(
        count, width, height, expected, FRAME_W, FRAME_H))
    if (width, height) != (FRAME_W, FRAME_H):
        raise ValueError("taille d'image inattendue")
    if abs(count - expected) > 2:
        print("ATTENTION : le nombre d'images diffère, l'alignement est à vérifier.")
    return count


# -- tuiles --------------------------------------------------------------------------------------

def tile_origins(width=FRAME_W, height=FRAME_H, tile=TILE):
    """Coins haut-gauche de tuiles qui couvrent l'image en se chevauchant.

    1920x1080 avec des tuiles de 320 : 7 colonnes x 4 lignes, chevauchement d'environ 50 px,
    pour qu'un ballon à cheval sur une frontière soit entier dans au moins une tuile.
    """
    def starts(size):
        count = int(np.ceil((size - tile) / (tile * 0.85))) + 1
        return np.unique(np.linspace(0, size - tile, count).round().astype(int)).tolist()
    return [(x, y) for y in starts(height) for x in starts(width)]


PLAYER_MARGIN_PX = 60


def player_tiles(matrix, players_m, pitch, origins, tile=TILE, margin=PLAYER_MARGIN_PX):
    """Les tuiles proches d'au moins un joueur suivi : le ballon en jeu est rarement ailleurs.

    Mesuré sur le match, sans vérité terrain : avec une marge de 60 px on ne garde qu'une tuile
    sur deux en moyenne, et le ballon du tracking est dans une tuile gardée 97 % du temps.
    Si aucun joueur n'est suivi, toutes les tuiles sont gardées.
    """
    players = np.asarray(players_m, dtype=np.float64)
    seen = ~np.isnan(players[:, 0])
    if not seen.any():
        return list(origins)
    pts = np.stack([players[seen, 0] / pitch[0], players[seen, 1] / pitch[1],
                    np.ones(int(seen.sum()))], axis=1) @ matrix.T
    with np.errstate(invalid="ignore", divide="ignore"):
        u, v = pts[:, 0] / pts[:, 2], pts[:, 1] / pts[:, 2]
    kept = [(x, y) for x, y in origins
            if np.any((u > x - margin) & (u < x + tile + margin)
                      & (v > y - margin) & (v < y + tile + margin))]
    return kept or list(origins)


class BallDetector(object):
    """Enveloppe du modèle : image entière -> liste de (u, v, confiance, largeur, hauteur)."""

    def __init__(self, weights, classes, conf=0.05, batch=16, device=0, half=True):
        from ultralytics import YOLO

        self.model = YOLO(weights)
        self.classes = classes
        self.conf = conf
        self.batch = batch
        self.device = device
        self.half = half and device != "cpu"     # la demi-précision n'existe que sur GPU
        self.origins = tile_origins()

    def detect(self, frames, tiles=None):
        """Pour chaque image, les détections de ballon, triées par confiance décroissante.

        `tiles` donne, pour chaque image, les coins des tuiles à analyser (voir player_tiles) ;
        sans lui, toute l'image est analysée.
        """
        tiles_in, owner = [], []
        for index, frame in enumerate(frames):
            origins = self.origins if tiles is None else tiles[index]
            for x, y in origins:
                tiles_in.append(np.ascontiguousarray(frame[y:y + TILE, x:x + TILE]))
                owner.append((index, x, y))

        found = [[] for _ in frames]
        for start in range(0, len(tiles_in), self.batch):
            results = self.model.predict(
                tiles_in[start:start + self.batch], imgsz=IMGSZ, conf=self.conf,
                classes=self.classes, device=self.device, half=self.half, verbose=False)
            for offset, result in enumerate(results):
                index, x, y = owner[start + offset]
                boxes = result.boxes
                if boxes is None or len(boxes) == 0:
                    continue
                xyxy = boxes.xyxy.cpu().numpy()
                confs = boxes.conf.cpu().numpy()
                for (x0, y0, x1, y1), score in zip(xyxy, confs):
                    found[index].append((float(x + (x0 + x1) / 2), float(y + (y0 + y1) / 2),
                                         float(score), float(x1 - x0), float(y1 - y0)))
        return [_merge(sorted(items, key=lambda d: -d[2])) for items in found]


def _merge(detections, radius=8.0):
    """Le même ballon vu dans deux tuiles qui se chevauchent ne compte qu'une fois."""
    kept = []
    for det in detections:
        if all(np.hypot(det[0] - k[0], det[1] - k[1]) > radius for k in kept):
            kept.append(det)
    return kept


def make_detector(weights=None, conf=0.05, batch=16, device=0):
    """Le modèle affiné s'il existe (ou celui donné), sinon le modèle de base sur 'sports ball'."""
    if weights is None and os.path.isfile(FINETUNED_WEIGHTS):
        weights = FINETUNED_WEIGHTS
    if weights is None or os.path.basename(weights) == BASE_WEIGHTS:
        print("modèle de base {} (classe COCO 'sports ball')".format(BASE_WEIGHTS))
        return BallDetector(BASE_WEIGHTS, [COCO_SPORTS_BALL], conf, batch, device)
    print("modèle affiné : {}".format(weights))
    return BallDetector(weights, None, conf, batch, device)

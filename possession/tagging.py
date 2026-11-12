"""Lecture du Smart Tagging : phases de jeu et coups de pied arrêtés, en images vidéo.

Le fichier est un XML SportsCode. <start> et <end> sont des secondes depuis la première image de
la vidéo tactique, donc secondes x 25 = image vidéo.

Le tagging est automatique : c'est un indice, pas une vérité. Ses coups de pied arrêtés sont des
fenêtres de durée fixe (35 s, ou 5 s pour un coup d'envoi) posées autour de la reprise du jeu, pas
l'instant de la reprise lui-même.
"""

import difflib
import xml.etree.ElementTree as ET

from .data import AWAY, GAME, GAMES, HOME, require


def team_names(meta_path):
    """(domicile, extérieur), tels que les nomme le fichier de tracking."""
    root = ET.parse(meta_path).getroot()
    return tuple(team.findtext("Name") or "" for team in root.iter("Team"))


def side_of(tag_team, names):
    """HOME, AWAY, ou None si le tag ne nomme pas d'équipe ("N/A").

    Les deux fichiers n'écrivent pas forcément les clubs de la même façon, donc on prend le nom
    le plus ressemblant plutôt qu'une égalité stricte.
    """
    text = (tag_team or "").strip().lower()
    if not text or text == "n/a":
        return None
    ratios = [difflib.SequenceMatcher(None, text, name.strip().lower()).ratio()
              for name in names]
    return HOME if ratios[0] >= ratios[1] else AWAY


def load(game=GAME, data_dir=None):
    """[{code, type, side, start, end}] : codes et types en minuscules, images vidéo."""
    meta_path, tag_path = require(["atd_meta", "smart_tagging"], game, data_dir)
    names = team_names(meta_path)
    fps = GAMES[game]["fps"]

    events = []
    for instance in ET.parse(tag_path).iter("instance"):
        tags = {label.findtext("group"): label.findtext("text")
                for label in instance.findall("label")}
        events.append({
            "code": (instance.findtext("code") or "").strip().lower(),
            "type": (tags.get("Type") or "").strip().lower(),
            "side": side_of(tags.get("Team"), names),
            "start": int(round(float(instance.findtext("start")) * fps)),
            "end": int(round(float(instance.findtext("end")) * fps)),
        })
    return events

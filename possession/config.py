"""Tous les paramètres, au même endroit.

Ils sont fixés par bon sens footballistique, pas réglés sur la vérité terrain publique : 5 minutes
et 17 possessions ne permettent de choisir entre deux valeurs (voir EVALUATION.md), et le règlement
l'interdit. Les distances sont en mètres, les durées en images (25 images = 1 seconde).
"""

FPS = 25

# Nom du fichier produit dans evaluation/results/.
RUN_NAME = "tour5"

# -- qui contrôle le ballon ----------------------------------------------------------------------
# Un joueur "a" le ballon s'il est à moins de R_CONTROL_M du ballon. Si le joueur le plus proche de
# l'autre équipe est presque aussi près (écart < DUEL_MARGIN_M), c'est un duel : pas d'avis.
R_CONTROL_M = 2.0
DUEL_MARGIN_M = 0.5

# -- qui a frappé le ballon en dernier -----------------------------------------------------------
# Une frappe est un changement de vitesse du ballon d'au moins KICK_DV_MS entre les KICK_LAG images
# d'avant et celles d'après. La trajectoire fournie est lissée : sur 3 images presque rien ne
# dépasse 4 m/s, il faut une demi-seconde pour voir une passe partir. Mesuré sur le match entier,
# sans vérité terrain : ces valeurs donnent environ une frappe toutes les 3 s de jeu, attribuable
# à une équipe 4 fois sur 5, et d'accord à 89 % avec l'indice de proximité quand les deux existent.
KICK_LAG = 12
KICK_DV_MS = 6.0
KICK_RADIUS_M = 3.0
KICK_HOLD = 75

# -- jeu arrêté (D) ------------------------------------------------------------------------------
# Ballon vu en dehors des lignes, avec une marge pour l'imprécision du tracking.
OUT_MARGIN_M = 0.5
# Ballon immobile : il s'est déplacé de moins de STILL_DIST_M en STILL_LAG images, et cela dure au
# moins STILL_MIN_FRAMES images d'affilée.
STILL_DIST_M = 0.5
STILL_LAG = 25
STILL_MIN_FRAMES = 50

# Ballon perdu de vue pendant que les joueurs marchent. Mesuré sur le match entier, sans vérité
# terrain : dans les trous de plus de 5 s, la vitesse moyenne des joueurs est sous 1,5 m/s sur
# 82 % des images, contre 27 % quand le ballon est visible. Un trou d'au moins GAP_MIN_FRAMES
# images compte comme jeu arrêté de son début jusqu'à sa dernière image "lente".
SLOW_SPEED_MS = 1.5
SPEED_SMOOTH_FRAMES = 25
GAP_MIN_FRAMES = 75
# Les joueurs ne ralentissent que quelques secondes après la sortie du ballon : l'arrêt commence
# jusqu'à GAP_LEAD_FRAMES images avant la première image lente du trou.
GAP_LEAD_FRAMES = 50
# Ballon visible, mais la vitesse moyenne des joueurs reste sous STOP_SPEED_MS (bien en dessous
# du pas de marche, 1,4 m/s) pendant au moins STOP_MIN_FRAMES images : tout le monde attend.
STOP_SPEED_MS = 1.0
STOP_MIN_FRAMES = 50

# -- Smart Tagging -------------------------------------------------------------------------------
# Un tag de coup de pied arrêté est une fenêtre fixe posée autour de la reprise. Mesuré sur les
# profils moyens de vitesse et de visibilité du ballon autour des 53 tags : la reprise tombe
# environ 5 s après le début du tag (3,4 s pour un coup d'envoi, d'après les deux coups d'envoi
# publiés dans DATA.md).
RESTART_OFFSET = 125
KICKOFF_OFFSET = 85
# Le jeu est arrêté dans les TAG_DEAD_BEFORE images qui précèdent la reprise ; l'équipe du tag,
# quand elle est renseignée, a le ballon dans les TAG_TEAM_AFTER images qui la suivent.
TAG_DEAD_BEFORE = 100
TAG_TEAM_AFTER = 75
# Après un but, le jeu est arrêté de GOAL_DELAY images après le début du tag jusqu'au coup d'envoi.
GOAL_DELAY = 50

# Phases de jeu taguées (Build Up, Progression...) : l'équipe du tag attaque, donc a le ballon.
# Mesuré contre l'indice de contrôle du tracking, sans vérité terrain : l'accord est de 80 à 90 %
# dans les premiers 40 % de la fenêtre pour les codes ci-dessous, puis il tombe (les fenêtres
# débordent sur la suite de l'action). "Players in the box" (74 %) est écarté, et les codes
# "Defending..." sont les miroirs exacts des codes d'attaque : ils n'apportent rien de plus.
PHASE_CODES = ("build up", "progression", "creating chances", "long ball",
               "ball in final third", "ball in the box")
PHASE_FRACTION = 0.4

# -- poids des indices, par image ----------------------------------------------------------------
W_TEAM = 1.0        # une équipe contrôle seule le ballon
W_KICK = 0.5        # l'équipe a frappé le ballon en dernier (passe en route)
W_DEAD_OUT = 2.0    # ballon hors du terrain
W_DEAD_STILL = 1.0  # ballon immobile
W_DEAD_GAP = 0.5    # ballon perdu de vue, joueurs lents
W_DEAD_STOPPED = 0.5  # ballon visible, joueurs quasiment à l'arrêt
W_TAG_DEAD = 1.0    # juste avant la reprise d'un coup de pied arrêté tagué
W_TAG_TEAM = 0.5    # équipe qui joue le coup de pied arrêté, juste après la reprise
W_FORCED_DEAD = 5.0 # avant un coup d'envoi (début de mi-temps, après un but)
# Volontairement faible : une phase seule (quelques secondes) ne peut pas payer SWITCH_COST. Elle
# départage quand le tracking n'a pas d'avis, par exemple pour choisir l'équipe à la reprise.
#
# Désactivé (0.0). Essayé à 0.03 au tour 3 : 1,1 % des images notées changent et rien ne montre un
# gain, donc on garde la version la plus simple. Remettre 0.03 pour réactiver l'essai.
W_PHASE = 0.0

# -- décodeur ------------------------------------------------------------------------------------
# Coût d'un changement d'état. Avec W_TEAM = 1, un changement d'équipe est validé après environ
# SWITCH_COST images de contrôle (0,4 s), et une touche adverse isolée de moins de 2 x SWITCH_COST
# images (0,8 s) est ignorée : "une simple touche sans contrôle ne change pas la possession".
#
# La première valeur essayée, 25, donnait 148 possessions de 39 s en moyenne sur le match : un
# indice d'équipe n'existe que sur 28 % des images, donc une seconde de contrôle "vu" est bien plus
# d'une seconde de jeu. 10 ramène la durée moyenne à 21 s, choisi sur ce seul critère de
# vraisemblance et non sur la vérité terrain.
SWITCH_COST = 10.0
# Où couper quand un changement d'équipe tombe dans un trou sans avis : 1.0 = à la fin du trou,
# 0.5 = au milieu. Le milieu est le choix qui minimise l'erreur quand on ne sait rien de plus.
SWITCH_PLACEMENT = 0.5

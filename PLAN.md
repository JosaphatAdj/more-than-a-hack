# Plan — possession du ballon (More than a Hack 2027)

Date limite : **17 novembre 2026**. Score à battre : spellF1 **0,2433** (`baseline_smooth50`).

## Principes

- **Un seul changement par tour**, mesuré avant de passer au suivant.
- **Aucune donnée externe, aucun entraînement** tant que les règles simples progressent.
- **Tout sort d'une seule commande**, de façon déterministe : `python -m possession.run` produit le CSV.
  Le règlement exige que le dépôt régénère exactement le même fichier.
- **Les 5 minutes publiques servent à vérifier, pas à régler.** Les paramètres viennent du bon sens
  footballistique et sont écrits une fois dans `possession/config.py`.
- **Confidentialité** : les données du match restent en local. Seuls des résultats agrégés (scores,
  comptages) sont lus dans la conversation avec l'assistant, jamais de lignes de tracking ni d'images.

## Organisation du code

```
possession/
  config.py      tous les paramètres, au même endroit
  data.py        lecture du tracking (ATD) -> tableaux numpy, avec cache
  emissions.py   indices par image (distances, ballon hors terrain, ballon immobile) -> scores H / A / D
  decode.py      décodeur Viterbi (3 états, coût de changement)
  run.py         la commande unique : données -> evaluation/results/<nom>.csv, plus un rapport
                 (nombre de possessions, durée moyenne, part de chaque lettre)
```

Environnement : `python -m venv .venv`, puis `.venv/Scripts/python -m pip install -r requirements.txt`.

Le tracking est lu une fois puis mis en cache local (`data/cache/*.npz`, ignoré par git), pour que
chaque essai prenne quelques secondes au lieu de quelques minutes.

## Tour 1 — notre propre baseline (tracking seul)

But : corriger les deux défauts connus de la baseline fournie, sans rien d'autre.

1. **Proposition par image**
   - Ballon visible et un joueur à moins de `R_CONTROL` (≈ 2 m) : son équipe est candidate.
   - Ballon visible mais loin de tout joueur (passe, ballon en l'air) : pas d'avis.
   - Ballon invisible : pas d'avis. **On ne répond plus `D`.**
2. **Jeu arrêté (`D`), version minimale**
   - Ballon hors des limites du terrain (avec une marge).
   - Ballon visible et immobile pendant plus de `T_STILL` secondes.
3. **Décodeur Viterbi** sur chaque mi-temps séparément
   - 3 états H / A / D, coût fixe à chaque changement d'état.
   - « Pas d'avis » = aucune préférence : l'état précédent se prolonge. C'est la règle « un ballon
     libre reste à la dernière équipe ».
4. **Sortie** : `X` hors des deux mi-temps, H / A / D dedans.

Livrable du tour 1 : `evaluation/results/tour1.csv`, validé par `validate_submission.py`, avec son
rapport (nombre de possessions, durée moyenne, part de `D`).

Critère de réussite : fichier valide, nombre de possessions plausible (quelques centaines sur le
match, durée moyenne de l'ordre de 10 à 20 s), et rien de cassé sur les 5 minutes publiques.

## Tour 2 — détection du jeu arrêté

Un `D` manqué fusionne deux possessions, un faux `D` en coupe une : c'est le plus gros levier.

- **Smart Tagging `SET PIECES`** : `D` dans les secondes qui précèdent la reprise ; équipe imposée à
  la reprise quand le tag `Team` est renseigné (les touches sont `N/A`).
- **Indices du tracking** : vitesse moyenne des joueurs faible, ballon près d'une ligne puis disparu,
  ballon réapparu immobile.
- **Buts** (`GOALS`) : `D` jusqu'au coup d'envoi suivant.

## Tour 3 — information d'équipe supplémentaire

- **Phases du Smart Tagging** (Build Up, Progression, Defending...) comme préférence douce pour H ou
  A quand le tracking n'a pas d'avis.
- **Forme collective** : l'équipe en possession est plus étalée et plus haute sur le terrain.

## Tour 4 — vidéo tactique (si les tours 1 à 3 plafonnent)

- **Quantité de mouvement dans l'image** (OpenCV, sans modèle) comme indice de jeu arrêté.
- **Détection du ballon** (YOLO / TrackNet) sur les images où le tracking l'a perdu, projetée sur le
  terrain avec l'homographie. À lancer sur la machine avec GPU.

## Tour 5 — rendu

- Figer la méthode au plus tard le 16 novembre.
- Dépôt public sans les données, dépendances figées, commande de reproduction dans le README.
- Document technique (approche, données utilisées et écartées, règles de possession, limites,
  reproduction).
- `validate_submission.py` sur le fichier exact envoyé, nommé `<nom_equipe>.csv`.

## À faire avant le tour 1

- [ ] Télécharger les données du match et les décompresser dans `data/` (ou définir `MTAH_DATA_DIR`).
- [ ] Installer les dépendances : `pip install -r requirements.txt` (pandas manque actuellement).
- [ ] Choisir le nom de l'équipe et créer le dépôt public.

## Journal des résultats

Scores sur les 5 minutes publiques (17 possessions) : un contrôle, pas un classement.

| essai | spellF1 | macroF1 | possessions (5 min) | possessions (match) | part de D (match) |
|---|---|---|---|---|---|
| baseline_smooth50 | 0,3256 | 0,6207 | 26 | — | — |
| tour1 (tracking + Viterbi) | 0,3871 | 0,5586 | 14 | 269 | 11,5 % |
| tour2 (+ ballon perdu et joueurs lents, + Smart Tagging) | 0,4471 | 0,7061 | 17 | 313 | 47,8 % |
| tour3 (+ phases taguées, poids 0,03) | 0,4235 | 0,7038 | 17 | 313 | 47,3 % |

Tour 3 : écart avec le tour 2 dans le bruit (une possession appariée en moins aux seuils bas, 1,1 %
des images modifiées). Phases désactivées par défaut (`W_PHASE = 0`), `tour2` reste la référence.
Le sens de déplacement collectif a été mesuré et écarté : il ne s'accorde avec l'équipe en contrôle
que 60 % du temps.
| tour4 (arrêts affinés + coupe au milieu du trou) | 0,4824 | 0,7670 | 17 | 301 | 48,6 % |

Tour 4, trois corrections mesurées une à une (spellF1 / macroF1 sur les 5 min) :
trous limités aux images lentes 0,459 / 0,717 ; + « tout le monde arrêté, ballon visible »
0,459 / 0,759 ; + changement d'équipe placé au milieu du trou sans avis 0,482 / 0,767.
`tour4` devient la référence. `tour2.csv` et `tour3.csv` ne sont plus reproductibles tels quels
(la règle des trous a changé) ; ils restent dans results/ pour mémoire.
| tour5 (+ dernier frappeur du ballon) | 0,5436 | 0,7587 | 22 | 334 | 48,3 % |

Tour 5 : frappes détectées par les changements de vitesse du ballon (fenêtre de 12 images, car la
trajectoire fournie est lissée). « La dernière équipe à avoir frappé » donne un avis pendant les
passes : la couverture des images à ballon visible passe de 51 % à 81 %. Retard moyen des
changements : de −8 à −3 images. `tour5` devient la référence.

Pistes mesurées sur le match entier et écartées :
- visée de la caméra (homographie) comme substitut du ballon : elle ne le suit qu'à 12 m près ;
- sens du panoramique de la caméra : d'accord avec l'équipe en contrôle 55 à 70 % du temps ;
- sens de déplacement collectif des joueurs : 60 %.
- modèle auto-entraîné (ballon caché, joueurs seuls, 105 indicateurs avec fenêtres de temps,
  entraîné sur une mi-temps et testé sur l'autre) : il retrouve la bonne équipe 83 % du temps sur
  les images sûres. Branché comme indice faible, il ne change pas le spellF1 des 5 minutes quand il
  est limité aux images sans ballon (macroF1 +0,015), et il le dégrade quand il s'applique plus
  largement, car ses indicateurs lissés brouillent l'instant des changements. Non intégré.

Le tracking seul est considéré comme épuisé : la suite est la vidéo (tour vidéo du plan).

## Vidéo (17 novembre)

- YOLO abandonné pour ce rendu : pas de GPU sur la machine de travail, et PyTorch impossible à
  télécharger (réseau à environ 12 Ko/s, soit plusieurs heures). Les scripts `video/` restent
  prêts pour une machine avec GPU.
- Cibles : sur les 64 643 images notées sans ballon, 55 553 portent déjà un indice d'arrêt ;
  seules 8 883 n'ont aucun avis (`python -m video.targets`).
- Détecteur classique OpenCV (objet petit et clair, mouvement entre images) testé en simulant des
  trous sur des passages où le tracking voit le ballon : à 1 s il fait moins bien qu'une simple
  interpolation (61 % contre 67 % à moins de 20 px), à 2 s un peu mieux (52 % contre 39 %), à 3 s
  les deux échouent (moins de 30 %). Pas assez fiable : non intégré. `tour5` reste la soumission.

## Tour 6 : revue des règles discutables (17 novembre)

Chaque règle jugée discutable est mesurée sur le match entier, sans vérité terrain. Aucune ne
justifie un changement : **pas de tour 6**, `tour5` reste la version du package.

- **Arrêt forcé après un but** (4 buts, 71 à 251 s jusqu'au coup d'envoi) : au début du tag, les
  joueurs marchent déjà (0,3 à 1,2 m/s ; 2,3 m/s pour le 4e but, juste après une attaque à
  4 m/s), puis le ballon repart vers le rond central. Le tag commence bien au but : règle gardée.
- **Ballon immobile 2 s** : 1,6 % des images, 23 séries. Le cas du gardien qui tient le ballon
  (surface, joueur au contact, joueurs qui courent) touche 0,02 % des images : règle gardée.
- **Ballon perdu + joueurs lents** : 34 % des images notées, 48 % de D au total. Cela donne
  environ 55 min de jeu effectif sur 106 min notées, dont 11 min d'arrêt après les buts. C'est
  l'ordre de grandeur habituel d'un match. Les 20 % de D des 5 minutes publiques viennent d'un
  passage très actif : règle gardée.
- **Instant de reprise fixe (5 s après le début du tag)** : on l'a remplacé, tag par tag, par la
  première frappe attribuable. Sur les corners, l'équipe du frappeur ne correspond à celle du tag
  que 3 fois sur 11, car le ballon est invisible au point de corner 83 % du temps. Détection
  non fiable : décalage fixe gardé.
- **Équipe des touches (tag « N/A »)** : on l'a déduite de l'équipe en possession avant l'arrêt,
  en testant cette idée sur les tags dont l'équipe est connue. Elle tient pour les corners
  (9 sur 12), mais pas pour les six mètres (6 sur 10, proche du hasard). Non intégré.
- **Dernier frappeur et déviations** : 1 033 frappes détectées, dont 855 attribuables. Sur 82
  frappes adverses isolées, 3 seulement sont suivies d'une reprise en moins de 1 s. Une
  frappe isolée ne vaut que 0,5 point par image : il faut 20 images pour payer un changement de
  coût 10, donc le décodeur ignore déjà les déviations brèves. Règle gardée.

# Règles de possession utilisées (version finale, équipe Goal Tensor)

Ce document décrit les règles de la version finale (SAM3), appliquées par le notebook `mtah-2027-final.ipynb` pour produire
`submission.csv`. Il ne faut pas le confondre avec `RULES.md` (le règlement du challenge). Les
durées sont en images : 25 images = 1 seconde. La version numpy seule (package `possession/`) est décrite dans `REGLES_POSSESSION.md`. Pour une version encore plus ancienne (joueur le plus proche +
vote majoritaire + modèle ML « ballon mort »), voir l'historique git.

**Entrées :** tracking ATD, vidéo tactique et homographie (SAM3 seulement). Aucun modèle entraîné,
aucune vérité terrain dans les règles. Le Smart Tagging n'est pas utilisé.

## 1. Principe

1. **Indices image par image.** Chaque règle ajoute des points à l'un des états `H` (Barcelone),
   `A` (Athletic) ou `D` (jeu arrêté). Une image sans point est **sans avis** (ballon invisible, duel).
2. **Décodeur de Viterbi** par mi-temps : il choisit la suite d'états qui récolte le plus de points,
   avec un coût fixe `SWITCH_COST` par changement d'état, et prolonge l'état précédent sur les
   images sans avis. Images hors mi-temps : `X`.

## 2. Indices H et A

| Règle | Condition | Poids |
|---|---|---|
| Contrôle de près | ballon visible, joueur à moins de 2 m, plus proche adversaire à au moins 0,5 m de plus | 1,0 |
| Dernier frappeur | pic local d'écart de vitesse du ballon ≥ 6 m/s entre les 12 images avant et après ; attribué au joueur le plus proche s'il est à moins de 3 m et à plus de 0,5 m du premier adversaire ; l'équipe reçoit ce poids par image jusqu'à la frappe suivante, 3 s au maximum | 0,5 |

L'avis du dernier frappeur s'éteint si une frappe n'est pas attribuable, si le ballon disparaît ou
si un indice d'arrêt apparaît. Un duel (écart < 0,5 m) ne donne aucun point.

## 3. Indices d'arrêt (D)

Sur toute image portant un indice d'arrêt, le contrôle de près et le dernier frappeur sont ignorés.

| Indice | Condition | Poids |
|---|---|---|
| Ballon hors du terrain | ballon ATD à plus de 0,5 m au-delà d'une ligne | 2,0 |
| Ballon immobile | déplacé de moins de 0,5 m en 1 s, pendant au moins 2 s | 1,0 |
| Ballon perdu, joueurs lents | trou ATD ≥ 3 s ; vitesse moyenne des joueurs (lissée sur 1 s) < 1,5 m/s, plus les 2 s avant la première image lente | 0,5 |
| Tout le monde à l'arrêt | ballon visible, vitesse moyenne des joueurs < 1 m/s pendant au moins 2 s | 0,5 |

Le reste d'un trou ATD où les joueurs courent reste sans avis.

## 4. Décodeur

- **Coût de changement.** Il a été balayé sur 5, 10, 15, 25 et 40 ; la version finale utilise **25**
  (choisi sur les 5 minutes publiques, donc optimiste ; le coût 10 donne 0,793 / 0,530 / 23 possessions).
  Une touche adverse isolée trop courte ne paie pas l'aller et le retour et est ignorée.
- **Placement des changements.** Entre deux équipes : coupure au milieu de la série d'images sans avis.
  Vers ou depuis `D` : coupure à la fin de la série.

## 5. Ballon manquant : SAM3

Là où le ballon ATD manque (en mi-temps, sans indice d'arrêt), les détections SAM3 « soccer ball »
sont filtrées et choisies par Viterbi (a priori de taille via l'homographie, a priori de mouvement,
pénalité de couleur), puis lissées par Kalman/RTS. Sur les images à ballon vivant : ATD 89,3 %,
SAM3 6,0 %, inconnu 4,7 %. Lancer la détection : voir `README.md`.

## 6. Résultats (5 minutes publiques, 17 possessions)

| Version | macroF1 | spellF1 | Possessions |
|---|---|---|---|
| `baseline_smooth50` (officielle) | 0,621 | 0,326 | 26 |
| V4 : contrôle + frappeur + arrêts (sans SAM3), coût 25 | 0,808 | 0,563 | 15 |
| **V6 : + SAM3 (final), coût 25** | **0,825** | **0,563** | 15 |

SAM3 améliore macroF1 de façon cohérente mais pas spellF1. Les écarts de spellF1 inférieurs à
environ 0,05 (une possession) sont dans le bruit.

## 7. Limites

- Ballon invisible sur une grande part des images : l'état précédent est prolongé.
- Arrêts brefs (touche jouée vite) manqués ; possessions très courtes ignorées par construction.
- Réglages (coût de changement) sélectionnés sur 17 possessions publiques.
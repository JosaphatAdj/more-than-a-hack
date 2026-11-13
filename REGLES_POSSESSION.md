# Règles de possession utilisées (version `tour5`)

Ce document décrit les règles que notre code applique aujourd'hui pour produire
`evaluation/results/tour5.csv`. Il ne faut pas le confondre avec `RULES.md`, qui contient le
règlement du challenge.

Pour régénérer le fichier : `python -m possession.run`. Le fichier produit est identique à chaque
exécution ; c'est vérifié par comparaison octet par octet.

Tous les paramètres cités sont dans [`possession/config.py`](possession/config.py). Les durées
sont en images : 25 images font 1 seconde.

---

## 1. Le principe en deux étapes

1. **Des indices image par image.** Pour chaque image, chaque règle peut ajouter des points à
   l'un des trois états : `H` (Barcelone a le ballon), `A` (Athletic a le ballon) ou `D` (jeu
   arrêté). Une image sans aucun point est une image **sans avis** : ballon invisible, ballon en
   l'air loin de tout joueur, duel. C'est le cas d'environ la moitié des images.
2. **Un décodeur sur toute la mi-temps.** Il choisit la suite d'états qui récolte le plus de
   points, en payant un coût fixe à chaque changement d'état. Il produit ainsi des blocs propres,
   sans clignotement, et il prolonge l'état précédent sur les images sans avis.

Les deux mi-temps sont décodées séparément. Hors des deux mi-temps (avant le match, la pause et
après le match), on écrit `X` : ces images ne sont pas notées.

**Seules entrées utilisées :** le tracking (ATD) et le Smart Tagging de la caméra tactique.
Ni la vidéo, ni l'homographie, ni la caméra TV, ni aucune donnée externe, ni la vérité terrain.

---

## 2. Qui a le ballon : indices pour `H` et `A`

### 2.1 Contrôle de près — poids 1,0

Le ballon est visible et un joueur se trouve à moins de **2 m** (`R_CONTROL_M`). Son équipe
reçoit 1 point si son plus proche adversaire est plus loin d'au moins **0,5 m**
(`DUEL_MARGIN_M`). Sinon, c'est un duel et personne ne reçoit de point.

Les distances sont calculées en mètres, sur un terrain de 105,3 × 68 m.

Couverture : 26,5 % des images notées (16,3 % pour le domicile, 10,2 % pour l'extérieur).

### 2.2 Dernier frappeur — poids 0,5

C'est ce qui donne un avis **pendant une passe**, quand le ballon voyage loin de tout joueur.

- **Une frappe** (passe, tir, contrôle orienté) est un changement brusque de vitesse du ballon :
  au moins **6 m/s** (`KICK_DV_MS`) d'écart entre sa vitesse sur les **12 images** d'avant et sur
  les 12 d'après (`KICK_LAG`). On ne garde que le pic local.
  - On mesure sur une demi-seconde parce que la trajectoire fournie est lissée : sur 3 images,
    presque aucune frappe ne se voit.
- **La frappe est attribuée** au joueur le plus proche s'il est à moins de **3 m**
  (`KICK_RADIUS_M`) et nettement plus près que le premier adversaire (écart de plus de 0,5 m).
- **Jusqu'à la frappe suivante,** l'équipe du frappeur reçoit 0,5 point par image, pendant
  **3 s** au maximum (`KICK_HOLD`).
- **L'avis s'éteint** si une frappe ne peut être attribuée, si le ballon disparaît ou si un
  indice d'arrêt apparaît.

Mesures sur le match entier, sans vérité terrain : 973 frappes, une toutes les 3 s de jeu
environ, dont 79 % attribuables à une équipe. Quand cet indice et le contrôle de près existent
tous les deux, ils désignent la même équipe 89 % du temps.

Couverture : 25 % des images notées.

### 2.3 Équipe du coup de pied arrêté — poids 0,5

Après la reprise d'un coup de pied arrêté du Smart Tagging dont l'équipe est renseignée, cette
équipe reçoit 0,5 point par image pendant **3 s** (`TAG_TEAM_AFTER`). La position de la reprise
est expliquée au point 3.5.

L'équipe n'est renseignée que pour les corners, les coups francs et les dégagements du gardien.
**Les touches sont toutes taguées `N/A`.**

Les noms de club diffèrent entre les deux fichiers (« Atletic Club » d'un côté) : on retient le
nom le plus ressemblant.

---

## 3. Jeu arrêté : indices pour `D`

**Règle commune :** sur toute image qui porte un indice de ballon hors du terrain, de ballon
immobile ou de joueurs à l'arrêt, le contrôle de près et le dernier frappeur sont ignorés. Le
joueur qui touche alors le ballon est celui qui va tirer le coup franc ou faire la touche, ce
n'est pas une possession.

| Indice | Condition | Poids |
|---|---|---|
| Ballon hors du terrain | ballon vu à plus de 0,5 m au-delà d'une ligne (`OUT_MARGIN_M`) | 2,0 |
| Ballon immobile | ballon déplacé de moins de 0,5 m en 1 s, pendant au moins 2 s d'affilée | 1,0 |
| Ballon perdu, joueurs lents | voir 3.3 | 0,5 |
| Tout le monde à l'arrêt | ballon visible, vitesse moyenne des joueurs sous 1 m/s pendant au moins 2 s | 0,5 |
| Avant une reprise taguée | les 4 s qui précèdent la reprise d'un coup de pied arrêté | 1,0 |
| Avant un coup d'envoi | début de mi-temps et après un but, jusqu'au coup d'envoi | 5,0 |

### 3.1 Ballon hors du terrain

Couverture : 2,1 % des images notées.

### 3.2 Ballon immobile

Couverture : 1,6 % des images notées.

### 3.3 Ballon perdu de vue, joueurs lents

C'est l'indice d'arrêt qui couvre le plus d'images (34 %). Il porte sur les trous d'au moins
**3 s** (`GAP_MIN_FRAMES`) pendant lesquels le tracking ne voit pas le ballon.

- On mesure la vitesse moyenne des joueurs suivis, lissée sur 1 s.
- Dans ces trous, les images où elle passe sous **1,5 m/s** (`SLOW_SPEED_MS`) comptent comme jeu
  arrêté. Pour comparaison, le pas de marche est d'environ 1,4 m/s.
- Les **2 s** qui précèdent la première image lente du trou comptent aussi (`GAP_LEAD_FRAMES`),
  car les joueurs ne ralentissent qu'un peu après la sortie du ballon.
- Le reste du trou, où les joueurs courent, reste **sans avis** : le jeu peut continuer sans que
  le ballon soit vu.

Pourquoi 1,5 m/s : mesuré sur le match entier, les joueurs sont sous ce seuil dans 82 % des
images des longs trous, contre 27 % quand le ballon est visible.

### 3.4 Tout le monde à l'arrêt, ballon visible

Il couvre les arrêts où le tracking voit encore le ballon, par exemple pendant qu'on prépare un
coup franc. Le seuil de 1 m/s est bien inférieur au pas de marche.

Couverture : 3,7 % des images notées.

### 3.5 Coups de pied arrêtés du Smart Tagging

Le Smart Tagging fournit 59 coups de pied arrêtés. Ce sont des fenêtres de **durée fixe**
(35 s, ou 5 s pour un coup d'envoi), qui ne marquent pas l'instant précis de la reprise.

Pour situer la reprise, on a établi le profil moyen de la vitesse des joueurs et de la
visibilité du ballon autour des 53 tags. La reprise tombe environ **5 s après le début du tag**
(`RESTART_OFFSET`), et **3,4 s** pour un coup d'envoi (`KICKOFF_OFFSET`, calé sur les deux coups
d'envoi publiés dans `DATA.md`).

- **Avant la reprise :** 1 point `D` par image pendant les 4 s qui précèdent
  (`TAG_DEAD_BEFORE`).
- **Après la reprise :** équipe du tag pendant 3 s, comme décrit au point 2.3.

### 3.6 Coups d'envoi et buts : arrêt forcé

Le poids de 5 est assez fort pour l'emporter sur tous les autres indices.

- **Début de chaque mi-temps :** arrêt jusqu'au coup d'envoi tagué de cette mi-temps.
- **Après chacun des 4 buts tagués :** arrêt à partir de 2 s après le début du tag
  (`GOAL_DELAY`) et jusqu'au coup d'envoi suivant.

---

## 4. Le décodeur

### 4.1 Coût d'un changement — `SWITCH_COST = 10`

Chaque changement d'état coûte 10 points. Avec le contrôle de près à 1 point par image, cela
donne deux conséquences :

- **Une touche adverse isolée de moins de 0,8 s est ignorée.** Elle ne rapporte pas assez pour
  payer l'aller et le retour (2 × 10 points). C'est la traduction du règlement : « une simple
  touche sans contrôle ne change pas la possession ».
- **Un contrôle adverse durable fait basculer la possession** dès qu'il a rapporté plus que le
  coût d'un changement.

Pourquoi 10 : avec 25, on obtenait 148 possessions de 39 s en moyenne sur le match, ce qui est
invraisemblable. Avec 10, la durée moyenne tombe à une dizaine de secondes. Ce choix repose sur
le nombre et la durée des possessions du match entier, pas sur la vérité terrain.

### 4.2 Images sans avis

Elles ne rapportent de points à aucun état. Le décodeur n'a donc aucune raison d'y changer
d'état et prolonge l'état précédent. C'est la règle du challenge : **un ballon libre ou disputé
reste à la dernière équipe qui l'avait.**

### 4.3 Placement exact des changements

Entre deux blocs, il y a souvent une série d'images sans avis. Le décodeur obtient le même total
où qu'il coupe dans cette série, donc on tranche par une règle :

- **Changement d'une équipe à l'autre :** coupure **au milieu** de la série
  (`SWITCH_PLACEMENT = 0.5`). Sans autre information, c'est le choix qui minimise l'erreur
  moyenne.
- **Changement vers ou depuis le jeu arrêté :** coupure **à la fin** de la série. L'arrêt
  commence à son premier indice et la possession reprend au premier contrôle.

---

## 5. Résultats

### 5.1 Sur le match entier (sans vérité terrain)

| | `tour5` |
|---|---|
| Barcelone en possession | 31,4 % des images notées |
| Athletic en possession | 20,2 % |
| Jeu arrêté | 48,3 % |
| Nombre de possessions | 334 |
| Durée moyenne d'une possession | 9,8 s |

### 5.2 Sur les 5 minutes publiques (17 possessions)

Ce contrôle sert à vérifier que rien n'est cassé. Il ne classe pas les méthodes : à cette
échelle, un écart de 0,05 en spellF1 correspond à une seule possession.

| Version | spellF1 | macroF1 | Possessions prédites |
|---|---|---|---|
| `baseline_smooth50` (officielle) | 0,3256 | 0,6207 | 26 |
| `tour1` : contrôle de près + décodeur | 0,3871 | 0,5586 | 14 |
| `tour2` : + ballon perdu, joueurs lents + Smart Tagging | 0,4471 | 0,7061 | 17 |
| `tour4` : arrêts affinés + coupure au milieu | 0,4824 | 0,7670 | 17 |
| **`tour5` : + dernier frappeur** | **0,5436** | **0,7587** | **22** |

Seul `tour5` peut être régénéré par le code actuel. Les autres fichiers restent dans
`evaluation/results/` pour mémoire.

---

## 6. Règles essayées puis écartées

Chacune a été mesurée, et aucune n'a apporté de gain qui sorte du bruit.

| Règle | Raison de l'abandon |
|---|---|
| Phases du Smart Tagging (Build Up, Progression…) | 1,1 % des images changent, aucun gain visible. Code conservé avec `W_PHASE = 0` |
| Codes « Defending… » du Smart Tagging | miroirs exacts des codes d'attaque, aucune information en plus |
| Sens de déplacement collectif des joueurs | désigne la bonne équipe 60 % du temps seulement |
| Visée de la caméra (homographie) à la place du ballon | elle ne suit le ballon qu'à 12 m près |
| Sens du panoramique de la caméra | désigne la bonne équipe 55 à 70 % du temps seulement |
| Modèle auto-entraîné sur les joueurs seuls | 83 % de bonnes réponses, mais aucun gain en spellF1 une fois branché, et une perte s'il s'applique largement |

---

## 7. Limites connues

- **Le ballon est invisible sur 41 % des images notées.** Pendant ces trous, quand les joueurs
  courent, le code n'a aucun avis et prolonge l'état précédent. Un changement de possession qui
  survient dans un tel trou est placé au mieux au milieu.
- **Les arrêts brefs, ballon visible et joueurs en mouvement, sont manqués.** C'est le cas d'une
  touche jouée vite, par exemple. Sur les 5 minutes publiques, 57 % des images de jeu arrêté
  sont retrouvées.
- **Les touches n'ont pas d'équipe dans le Smart Tagging,** donc rien n'indique quelle équipe
  reprend le jeu après une touche.
- **Les possessions de moins de 0,8 s sont ignorées** par construction. Les 5 minutes publiques
  en contiennent deux (0,8 s et 1,3 s).
- **Les réglages s'appuient en partie sur l'observation des 5 minutes publiques.** Aucun seuil
  n'a été optimisé dessus, mais le diagnostic du tour 4 a été mené en comparant nos changements
  à ceux de ces 5 minutes. Il faudra le dire dans le document technique.

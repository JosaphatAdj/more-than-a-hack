# Détection du ballon dans la vidéo — mode d'emploi pour le PC avec GPU

But : retrouver le ballon sur les images où le tracking l'a perdu (41 % des images notées), et
produire un petit fichier `data/cache/ball_video.csv` que `possession/` utilisera pour combler
ces trous.

**État du code.** Vérifié sur la vraie vidéo, sans GPU : lecture des images, alignement avec le
tracking, homographie, tuiles et fabrication des exemples (`make_dataset`). **Jamais exécuté :
l'appel au modèle YOLO** (`evaluate`, `train`, `detect`). La première exécution de ces trois
scripts est donc aussi un test du code : en cas d'erreur, copier le message complet.

Toutes les commandes se lancent depuis la racine du dépôt, dans PowerShell.

## 0. Avant de commencer

- Brancher le PC sur secteur et désactiver la mise en veille : certaines étapes durent des heures.
- Pilote NVIDIA à jour (GeForce Experience ou nvidia.com).
- Python 3.12 de préférence. PyTorch n'est pas toujours disponible pour la toute dernière version
  de Python ; si l'étape 3 échoue avec une version plus récente, installer Python 3.12.
- Git installé.

## 1. Récupérer le code

```powershell
git clone https://github.com/JosaphatAdj/more-than-a-hack.git
cd more-than-a-hack
```

## 2. Copier les données

Dans `data\tactical\`, avec ces noms exacts :

```
BAR-ATH_tactical.mp4
BAR-ATH_tactical_homography.csv
BAR-ATH_tactical_atd.xml
BAR-ATH_tactical_atd.txt
BAR-ATH_tactical_smart_tagging.xml
```

Rien de ce dossier ne part sur GitHub : `data/` est ignoré par git.

## 3. Installer

```powershell
python -m venv .venv-video
.venv-video\Scripts\Activate.ps1
```

PyTorch **avec CUDA** d'abord. Prendre la commande exacte sur https://pytorch.org/get-started/locally/
(choisir Stable, Windows, Pip, Python, CUDA). Elle ressemble à ceci, le suffixe `cu…` changeant
selon la version :

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

Puis le reste :

```powershell
pip install -r requirements-video.txt
```

Vérifier que le GPU est vu. La commande doit afficher `True` puis le nom de la carte :

```powershell
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

Si elle affiche `False`, PyTorch est en version CPU : refaire l'installation de PyTorch ci-dessus.

## 4. Tester le modèle de base (10 à 20 minutes)

```powershell
python -m video.evaluate --base
```

La première fois, le tracking est relu (une à deux minutes) et les poids `yolo11s.pt` sont
téléchargés. Le script affiche un tableau :

```
  seuil de confiance   trouvé   1er choix   fausses par image
      0.05             ...
```

**Le chiffre à regarder est « 1er choix » au seuil 0.05 et 0.25.**

- au-dessus de 70 % : passer directement à l'étape 6 ;
- en dessous : faire l'étape 5. C'est le cas le plus probable, car le ballon ne fait que 4 à 11
  pixels dans cette vidéo et le modèle de base n'a jamais vu de ballon aussi petit.

## 5. Affiner le modèle (1 à 2 heures)

```powershell
python -m video.make_dataset      # environ 10 min : fabrique les exemples, sans annotation humaine
python -m video.train             # 30 à 60 min sur une RTX 3050
python -m video.evaluate          # teste le modèle affiné sur des minutes jamais vues
```

- `make_dataset` écrit environ 8 000 petites images dans `data\cache\yolo_ball\` (moins de 1 Go).
- Si `train` s'arrête sur « CUDA out of memory » : `python -m video.train --batch 8`.
- Si le « 1er choix » reste sous 50 % après affinage, la détection n'apportera probablement rien :
  s'arrêter là et le signaler.

## 6. Détecter le ballon dans les trous (plusieurs heures)

Commencer par une image sur deux :

```powershell
python -m video.detect --step 2
```

Le script affiche sa progression toutes les 2 000 images, ce qui permet d'estimer la durée totale
(environ 32 000 images à traiter avec `--step 2`). En cas d'interruption :

```powershell
python -m video.detect --step 2 --resume
```

Résultat : `data\cache\ball_video.csv`, quelques Mo.

## 7. Rapporter le résultat

- Copier `data\cache\ball_video.csv` dans le même dossier `data\cache\` du PC où tourne
  `possession/` (clé USB ou autre moyen privé). **Ne pas le mettre sur GitHub** : c'est une donnée
  dérivée du match.
- Noter les tableaux affichés par `video.evaluate` : ce sont eux qui disent quelle confiance
  accorder aux détections, et donc comment les utiliser.

## Ce que fait chaque script

| Script | Rôle |
|---|---|
| `evaluate.py` | cache le ballon du tracking, demande au modèle de le retrouver, mesure |
| `make_dataset.py` | fabrique des exemples à partir du tracking et de l'homographie |
| `train.py` | affine `yolo11s.pt` sur ces exemples |
| `detect.py` | cherche le ballon sur les images où le tracking ne le voit pas |
| `common.py` | homographie, lecture de la vidéo, tuiles, appel du modèle |

Deux choix à connaître :

- **Tuiles de 320 px agrandies à 640.** Le ballon double de taille avant d'être analysé.
- **Recherche près des joueurs seulement.** On n'analyse que les tuiles situées à moins de 60 px
  d'un joueur suivi : deux fois moins de travail, et le ballon du tracking s'y trouve 97 % du
  temps. Pour tout analyser : ajouter `--everywhere`.

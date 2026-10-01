# 0004 - Organiser le code en paquet Python installable

## Statut
Accepté — 2026-09-30

## Contexte
Le code était rangé dans src/ (source) et seul pytest savait l'y trouver, grâce au réglage pythonpath = src
de pytest.ini. Dans un conteneur Docker ou en CI, Python n'aurait pas trouvé les modules(ModuleNotFoundError). Il aurait
fallu refaire ce réglage sur chaque environnement, et un oubli suffisait à tout casser.

## Décision
Organiser le code en paquet Python installable : 
1. Le code est rangé dans le dossier src/raceboard/.
2. Le fichier pyproject.toml sert de carte d'identité ; il donne le nom du paquet, sa version et ses dépendances.
3. Le paquet est installé avec pip install -e . en dev, et avec pip install . en production (Docker). On lance
   les modules avec `py -m raceboard.<module>`.

## Alternatives écartées
- Garder les scripts à plat dans src/ : dans Docker ou en CI, Python n'aurait pas trouvé les modules sans refaire un réglage de chemin sur chaque environnement.
- Réorganiser plus tard (étape e) : plus de modules à déplacer, donc une migration plus lourde et un risque plus grand de casser l'appli.

## Conséquences
- (+) Une seule commande standard (pip install .) installe RaceBoard partout, sur le PC, en CI et dans Docker, sans réglage de chemin.
- (−) La version de pyirsdk est notée à deux endroits (`pyproject.toml` et `requirements.txt`), qu'il faut garder cohérents.
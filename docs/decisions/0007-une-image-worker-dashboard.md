# 0007 — Une seule image pour le worker et le dashboard

## Statut
Accepté — 2026-11-05

## Contexte
RaceBoard a deux composants à conteneuriser : le worker, qui importe les `.ibt` en base
puis s'arrête, et le dashboard, qui affiche les tours lus en base et tourne en continu.
Ils partagent le même code d'accès à la base (`db.py`) et les mêmes paquets.
Il faut choisir entre une image commune et une image par composant.

## Décision
Une seule image `raceboard`, construite par un seul Dockerfile.
Son `CMD` par défaut lance le dashboard, parce que c'est un service qui tourne en continu.
Le worker se lance depuis la même image en remplaçant le `CMD` au lancement :
`docker run raceboard python -m raceboard.worker`.

## Alternatives écartées
- **Une image par composant (deux Dockerfiles)** : deux builds et deux images à maintenir
  pour un code et des paquets presque identiques, avec le risque qu'elles divergent.
- **Les deux composants dans un même conteneur** : un conteneur ne fait tourner qu'une commande ;
  il faudrait un programme de plus pour en gérer deux. Et on ne pourrait plus lancer
  le worker sans le dashboard, ce qui va contre la règle « les composants ne se parlent que par la base ».

## Conséquences
- (+) Un seul build, une seule image de 307 Mo à stocker et à envoyer (v0.3, v0.4).
- (+) Le worker et le dashboard utilisent toujours la même version de `db.py` : ils ne peuvent pas se désynchroniser.
- (−) L'image du worker embarque Streamlit, dont il ne se sert pas.
- (−) Lancer le worker demande de retaper sa commande complète (simplifié par docker compose à l'étape f).
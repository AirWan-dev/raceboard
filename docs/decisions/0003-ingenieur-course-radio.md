# 0003 — Créer un ingénieur de course radio, par règles puis par IA

## Statut
Accepté — 2026-09-27

## Contexte
Le moteur d'analyse et de stratégie de course avait été écarté du périmètre :
il exigeait une expertise d'ingénieur de course que je n'ai pas, pour une valeur infra nulle.

Deux éléments ont changé depuis :
- un LLM (modèle de langage interrogé via API) peut apporter l'expertise d'analyse ;
- le code applicatif est désormais délégué à Claude Code, l'infra restant construite à la main.

Par ailleurs, RaceBoard doit devenir une application que j'utiliserai dans la durée,
et pas seulement un support d'apprentissage.

## Décision
Créer un ingénieur de course radio qui tourne en local, sur le PC de jeu,
pendant la course, en lisant la télémétrie en direct via le SDK iRacing.

Développement par étapes :
1. **Version règles** : un script détecte un événement et pousse l'information au pilote.
2. **Version IA** : un LLM formule et priorise les messages ; les règles restent la source des événements.

La lecture du SDK est séparée de la logique des règles, afin de tester les règles
en rejouant un fichier `.ibt` enregistré, sans simulateur.

Le développement est délégué à Claude Code.

## Alternatives écartées
- **Moteur d'analyse codé à la main** : exige une expertise d'ingénieur de course que je n'ai pas.
- **IA dès le départ** : trop de nouveautés à la fois, et aucune version utile rapidement.
- **Débrief après session uniquement** : ne correspond pas à l'usage recherché, qui est d'être
  informé pendant la course.

## Conséquences
- (+) Application utile en course dès la version règles.
- (+) Un composant IA exploité en production, cohérent avec une orientation MLOps.
- (+) Règles testables en CI grâce au rejeu de `.ibt`.
- (−) Composant hors du pipeline cloud : il ne peut tourner que sur la machine où le simulateur est lancé.
- (−) Le SDK devient une deuxième source de données, à côté des fichiers `.ibt`.
- (−) Version IA : une clé d'API à protéger et des coûts d'appel à surveiller.
- L'ADR 0001 reste valable : le pipeline `.ibt` par lots est inchangé.
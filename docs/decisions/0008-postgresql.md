# 0008 — Passer de SQLite à PostgreSQL

## Statut
Accepté — 2026-11-10

## Contexte
SQLite stocke toute la base dans un seul fichier. En v0.2, le worker et le dashboard
tournent dans deux conteneurs et partagent la base via un volume.
SQLite n'accepte qu'une seule écriture à la fois : le fichier entier est verrouillé.
En v0.4, Azure fournira des serveurs PostgreSQL gérés, pas de fichier partagé fiable.
Plus tard, la gestion de ligue fera écrire plusieurs utilisateurs en même temps.

## Décision
La base devient un serveur PostgreSQL, ajouté comme 3e service du `docker-compose.yml`,
depuis l'image officielle `postgres`. Le worker et le dashboard s'y connectent par le réseau
de compose, en le désignant par son nom de service. `db.py` est adapté par Claude Code ;
le SQL reste portable.

## Alternatives écartées
- **Garder SQLite** : un fichier partagé supporte mal les accès simultanés et ne peut pas
  suivre l'appli dans le cloud.
- **MySQL / MariaDB** : valables, mais PostgreSQL est déjà prévu dans la stack, proposé
  en service géré sur Azure et sur AWS, et respecte le SQL standard.

## Conséquences
- (+) Plusieurs écritures en même temps.
- (+) Comptes et droits : le dashboard pourra avoir un compte en lecture seule.
- (+) Prépare le passage à Azure en v0.4.
- (−) Un premier mot de passe à gérer (voir ADR 0009).
- (−) Un service de plus à surveiller et à sauvegarder (v0.6).
- (−) Les 1 504 sessions sont à recharger en relançant le worker.
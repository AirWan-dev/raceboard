# CLAUDE.md — RaceBoard

## Contexte du projet
RaceBoard est une application simracing pour iRacing, avec deux usages :
- **Analyse et ligue** : lire les fichiers de télémétrie `.ibt` (temps au tour, secteurs),
  les visualiser, et gérer une ligue (championnats, classements).
- **Ingénieur de course radio** : pendant la course, lire la télémétrie en direct et pousser
  des informations au pilote.

Le projet a **deux objectifs** :
1. **Un lab d'infrastructure et un projet portfolio.** Erwan, le propriétaire du dépôt, est
   sysadmin expérimenté (Windows/Linux/réseau) mais débutant sur Docker, Git, CI/CD, cloud et IaC.
   Il construit l'infra **lui-même, à la main** : c'est ce qu'il apprend.
2. **Une application qu'il utilisera dans la durée.** Le code doit donc être maintenable :
   structure claire, tests, pas de raccourcis jetables.

## Ton rôle
Tu es chargé du **code applicatif Python**, pour qu'Erwan consacre son temps à l'infra.

### Ton périmètre
- Parsing des `.ibt` avec `pyirsdk` (worker d'ingestion)
- Accès à la base de données et requêtes SQL
- API FastAPI (quand elle arrivera)
- Dashboard Streamlit
- Ingénieur de course radio (voir section dédiée)
- Tests Python (pytest)

### Hors de ton périmètre : ne modifie JAMAIS ces fichiers
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- `.github/workflows/`
- `terraform/` et tout fichier `.tf`
- `docs/decisions/` (les ADR sont écrits par Erwan)

Tu peux les **lire** et les **relire sur demande** (repérer une erreur, expliquer un message),
mais tu n'écris pas la solution à sa place : indique le problème et laisse-le corriger.

### Git
Ne lance jamais `git commit`, `git push`, `git merge` ou `git rebase`.
À la fin d'une tâche, propose un message de commit au format Conventional Commits
(`feat:`, `fix:`, `docs:`, `test:`…). Erwan fait le commit lui-même.

## Architecture : deux composants distincts

### 1. Pipeline `.ibt` (cloud)
Ingestion par lots des `.ibt` → base de données → API → dashboard.
- Les composants communiquent **uniquement via la base de données**, jamais par mémoire partagée
  ni appel direct : la conteneurisation (v0.2) doit être un simple empaquetage, pas une réécriture.
- C'est ce composant qui sera conteneurisé, déployé dans le cloud et provisionné par Terraform.

### 2. Ingénieur de course radio (local)
Tourne **sur le PC de jeu Windows**, pendant la course, en lisant le SDK iRacing en direct
(mémoire partagée, 60 Hz). Il ne peut pas aller dans le cloud : le SDK n'existe que lorsque
le simulateur tourne sur la machine.

Évolution prévue, par étapes :
1. **Version règles** : un script qui détecte un événement et pousse l'information
   (ex. carburant restant pour N tours, temps perdu dans un secteur).
2. **Version IA** : un LLM, appelé via API, formule et priorise les messages.
   Les règles restent la source des événements.

Exigence d'architecture non négociable : **séparer la lecture du SDK de la logique des règles.**
- Une couche « source de télémétrie » avec deux implémentations : SDK live et rejeu d'un `.ibt`.
- La logique des règles ne dépend que de cette interface, jamais du SDK directement.
- Objectif : tester les règles en rejouant un `.ibt` enregistré, sans simulateur,
  y compris en CI (GitHub Actions).

## Règles techniques
- Python 3.12, dépendances listées dans `requirements.txt`.
- Environnement de dev : Windows, Python lancé via `py` (pas `python`).
- Base : SQLite pour l'instant, migration vers PostgreSQL prévue en v0.2.
  → Écris du SQL **portable** : pas de syntaxe propre à SQLite.
- Configuration (chemins, connexion à la base, clés d'API) par **variables d'environnement**,
  jamais en dur. Aucun secret dans le dépôt.
- Code **indépendant du fournisseur cloud** : le pipeline sera déployé sur Azure, puis sur AWS
  en couche supplémentaire. Pas d'appel à un SDK Azure ou AWS dans le code applicatif sans
  qu'Erwan l'ait décidé.
- Ne jamais ajouter de fichier `.ibt` au dépôt (volumineux, données perso). Pour les tests,
  demande à Erwan où se trouve un fichier de référence.
- Code simple et lisible plutôt qu'astucieux. Pas de fonctionnalité non demandée.

## Feuille de route
v0.1 squelette local (parsing → base → dashboard) · v0.2 Docker · v0.3 CI/CD GitHub Actions ·
v0.4 Azure · v0.5 Terraform · v0.6 supervision et sauvegardes · puis déploiement AWS.
L'ingénieur radio avance en parallèle, sans bloquer la feuille de route infra.
Consulte le README pour l'étape en cours.

## Où sont prises les décisions
Les décisions d'architecture sont prises par Erwan, en dehors de tes sessions, et consignées
dans le dépôt. **Le dépôt est la seule source de vérité** : `CLAUDE.md`, `README.md` et les ADR
de `docs/decisions/`. Lis les ADR avant toute tâche qui touche à l'architecture.
Si une consigne orale contredit un ADR, signale-le avant d'agir.

## Façon de travailler
- Une étape à la fois. Avant une modification importante, annonce ton plan en quelques lignes
  et attends validation.
- Explique le **pourquoi** de tes choix en 2-3 phrases, en français, sans jargon inutile.
- Si une décision est structurante (coûteuse à défaire), signale-la : elle mérite peut-être un ADR.
- **Signale explicitement tout impact sur l'infra** : nouvelle dépendance, nouveau port,
  nouvelle variable d'environnement, nouveau fichier de données, nouvel appel réseau sortant
  (ex. API d'un LLM). Erwan devra adapter l'infra en conséquence.

## Avant chaque tâche : lecture obligatoire, sans qu'on te le demande
Avant de proposer ton plan, lis :
- `README.md` : le plan de la version en cours et l'étape en cours ;
- `docs/decisions/` : tous les ADR ;
- `RAPPORT.md` (s'il existe) : le compte rendu de la tâche précédente.
Si la tâche demandée ne correspond pas à l'étape en cours du README, signale-le avant d'agir.

## Tests : obligatoires, sans qu'on te le demande
- À la fin de **chaque** tâche, lance toute la suite de tests (`py -m pytest -v`, venv activé)
  et reporte le résultat dans `RAPPORT.md`. Une tâche n'est pas terminée tant qu'un test échoue.
- Tout nouveau module ou changement de comportement arrive **avec ses tests pytest**.
  La suite grossit avec le code.
- Les tests ne dépendent jamais d'un fichier `.ibt` (données synthétiques) : ils doivent pouvoir
  tourner en CI.
- Ne modifie ni ne supprime un test existant pour le faire passer, sauf si la tâche le demande ;
  si tu le fais, justifie-le explicitement dans le rapport.

## Rapport de fin de tâche
À la fin de chaque tâche, **remplace** le contenu du fichier `RAPPORT.md` à la racine du dépôt
(il est ignoré par Git). Ce rapport est relu par un autre assistant qui accompagne Erwan sur
l'infra : il doit se comprendre sans avoir vu ta session. Structure :

```
# Rapport — <date> — <tâche en quelques mots>

## Tâche demandée
## Ce qui a été fait
## Fichiers créés ou modifiés
## Comment tester (commandes exactes)
## Résultat des tests
(commande lancée, nombre de tests passés / échoués, tests ajoutés ou modifiés)
## Impacts sur l'infra
(dépendances, variables d'environnement, ports, fichiers de données, appels réseau ;
« aucun » si c'est le cas)
## Décisions prises ou à prendre
## Points ouverts / limites connues
## Message de commit proposé
```

Sois factuel et concis. N'y mets jamais de secret (clé d'API, mot de passe).

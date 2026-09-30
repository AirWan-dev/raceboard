# RaceBoard — README / architecture

*Document de référence du projet. À tenir à jour au fil de la construction.*

## Objectif
Une application simracing qui transforme mes données de sessions **iRacing** en informations exploitables :
analyse des temps au tour et des secteurs, gestion de ligue, et un ingénieur de course radio pendant la course.

Deux objectifs, dans cet ordre :
1. **Un lab d'infrastructure et un projet portfolio.** RaceBoard est un prétexte réaliste pour apprendre
   Docker, CI/CD, cloud et IaC en construisant un vrai service, et en tirer une preuve pour mon CV.
   L'infra est construite **à la main**.
2. **Une application utilisée dans la durée.** Le code applicatif est délégué à **Claude Code**,
   encadré par le fichier `CLAUDE.md`.

## Ce que fait l'appli
- **Télémétrie / perf** : lire un fichier `.ibt` d'une session → temps au tour et par secteur → visualisation.
- **Ligue / résultats** : championnats, classements (CRUD multi-utilisateurs — bon terrain d'infra).
- **Ingénieur de course radio** : pendant la course, pousse des informations au pilote.
  D'abord par règles, ensuite par IA (voir ADR 0003).

## Architecture : deux composants

### 1. Pipeline `.ibt` (cloud)
- **Worker d'ingestion** : parse les `.ibt`, écrit en base.
- **Base de données** : SQLite au début, PostgreSQL ensuite.
- **API** : expose les données (FastAPI).
- **Front** : dashboard (Streamlit au début, Grafana ensuite).

Les composants communiquent uniquement via la base de données : la conteneurisation doit être
un simple empaquetage, pas une réécriture.

### 2. Ingénieur de course radio (local)
Tourne sur le PC de jeu Windows et lit le SDK iRacing en direct. Il ne peut pas aller dans le cloud :
le SDK n'existe que lorsque le simulateur tourne. La lecture du SDK est séparée de la logique des règles,
pour tester les règles en rejouant un `.ibt`, y compris en CI.

## Stack
Python · pyirsdk · SQLite → PostgreSQL · Streamlit → Grafana · Docker + docker-compose ·
GitHub Actions · Azure puis AWS · Terraform · Claude Code (code applicatif).

## Données iRacing
Trois sources : l'API `/data` (résultats de sessions terminées), le SDK (live 60 Hz, simulateur lancé),
et les fichiers **`.ibt`** (sauvegardés dans `iRacing/telemetry/`).
- Le pipeline utilise les `.ibt` (lots) : `pyirsdk` les lit **sans que le simulateur tourne**
  → développement possible partout, y compris en CI et dans le cloud (ADR 0001).
- L'ingénieur radio utilise le SDK (ADR 0003).

## Construction par couches
On ne passe à la couche suivante qu'une fois la précédente **réellement maîtrisée**.
- **v0.1** — squelette : parsing `.ibt` → base → dashboard (sur ma machine, sans conteneur).
- **v0.2** — conteneurs : Docker + docker-compose.
- **v0.3** — CI/CD : pipeline GitHub Actions (tests, build image).
- **v0.4** — cloud : déploiement sur Azure.
- **v0.5** — IaC : Terraform provisionne l'infra Azure.
- **v0.6** — exploitation : supervision, sauvegardes, reprise.
- **v0.7** — multi-cloud : déploiement sur AWS en couche supplémentaire.
- *En parallèle* : ingénieur de course radio, développé par Claude Code, sans bloquer la feuille de route infra.
- *En réserve* : environnements dev / staging / prod ; authentification / comptes.

## Règles de conception
- **Infra d'abord.** Je construis l'infra moi-même ; Claude Code écrit le code applicatif.
  Si je passe plus de temps sur l'appli que sur l'infra, c'est un signal d'alarme.
- Le dépôt est la **seule source de vérité** : `README.md`, `CLAUDE.md` et les ADR de `docs/decisions/`.
- Toute décision structurante fait l'objet d'un ADR.
- Toujours expliquer le **« pourquoi »** avant le **« comment »**.

## Décisions (ADR)
- 0001 — Utiliser les fichiers `.ibt` comme source de données
- 0003 — Créer un ingénieur de course radio, par règles puis par IA

## Plan de la v0.1 (étape en cours)
Chaque étape a un critère « terminé » vérifiable. On ne passe à la suivante que lorsqu'il est rempli.
Colonne « Qui » : **Erwan** = fait à la main ; **Claude Code** = code applicatif (voir `CLAUDE.md`).

| # | Étape | Qui | Terminé quand… | État |
|---|---|---|---|---|
| a | **État des lieux propre** : dépôt, venv, arborescence (`src/`, `data/`, `docs/`), suppression du dossier `dev` parasite | Erwan | `git status` propre, venv activé, `py --version` = 3.12 | ✅ terminé |
| b | **Lire un `.ibt`** : script qui ouvre un fichier avec `pyirsdk` et liste les variables disponibles | Claude Code | La liste des canaux s'affiche en console | ✅ terminé |
| c | **Extraire les tours** : temps au tour (puis secteurs) d'une session | Claude Code | Tableau des tours cohérent avec la session réelle | ✅ terminé |
| d | **Écrire en base** : schéma SQLite (sessions, tours), insertion | Claude Code | Une requête SQL renvoie les tours | ⏳ en cours |
| e | **Worker d'ingestion** : traite tous les `.ibt` d'un dossier, sans doublon si relancé | Claude Code | 2 lancements = même nombre de lignes | ⬜ |
| f | **Dashboard Streamlit** : lit la base (jamais les `.ibt` directement) | Claude Code | Page locale affichant les temps au tour | ⬜ |
| g | **Clôture v0.1** : `requirements.txt`, README à jour, tag Git `v0.1` | Erwan | Un clone neuf + 3 commandes = appli qui tourne | ⬜ |

Règles pour ce plan :
- Une étape = un périmètre. Ne pas anticiper une étape suivante (pas de base à l'étape c, pas de dashboard à l'étape d…).
- Les étapes ne se réordonnent pas et ne s'ajoutent pas sans décision d'Erwan.
- Seul Erwan met à jour la colonne « État ».

## État actuel
Dépôt Git en place, `CLAUDE.md` et ADR 0001 / 0003 poussés.
Étape en cours : **v0.1 — étape d** (écrire en base).

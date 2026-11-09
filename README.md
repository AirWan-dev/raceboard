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

## Installation
Prérequis : Windows, Python 3.12, Git. Toutes les commandes se tapent dans PowerShell.

1. Récupérer le projet
   ```
   git clone https://github.com/AirWan-dev/raceboard.git
   cd raceboard
   ```
2. Créer puis activer l'environnement Python (l'activation est à refaire dans chaque nouvelle fenêtre)
   ```
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Installer RaceBoard et ses dépendances
   ```
   py -m pip install -r requirements-dev.txt
   ```
   (requirements.txt seul ne suffit pas : la ligne `-e .`, qui installe RaceBoard lui-même, est dans requirements-dev.txt)
   
4. Configurer (dans la même fenêtre)
   ```
   $env:RACEBOARD_DB_PATH = "C:\chemin\vers\raceboard\data\raceboard.db"
   $env:RACEBOARD_TELEMETRY_DIR = "C:\Users\<vous>\Documents\iRacing\telemetry"
   ```
5. Importer les .ibt dans la base
   ```
   py -m raceboard.worker
   ```
6. Lancer le dashboard, puis ouvrir http://localhost:8501
   ```
   py -m raceboard.dashboard
   ```
## Construction par couches
On ne passe à la couche suivante qu'une fois la précédente **réellement maîtrisée**.
- **v0.1** — squelette : parsing `.ibt` → base → dashboard (sur ma machine, sans conteneur).
- **v0.2** — conteneurs : Docker + docker-compose.
- **v0.3** — CI/CD : pipeline GitHub Actions (tests, build image).
- **v0.4** — cloud : déploiement sur Azure.
- **v0.5** — IaC : Terraform provisionne l'infra Azure.
- **v0.6** — exploitation : supervision, sauvegardes, reprise.
- **v0.7** — multi-cloud : déploiement sur AWS en couche supplémentaire.
- **v0.8** — Sentinel : supervision assistée par IA, trois agents.
  - **Veilleur** : lit les logs des conteneurs listés dans `sentinel.yml`.
  - **Diagnosticien** : analyse une erreur détectée, cherche une solution dans la doc officielle / GitHub.
  - **Rapporteur** : rapport de santé + correctif *proposé* (script ou commande), **jamais exécuté** automatiquement.
  - Conçu **générique, piloté par config** : aucun nom propre à RaceBoard dans le code → réutilisable sur OpenSport, WealthOS, etc.
    Extraction dans son propre dépôt une fois stable. ADR à rédiger au démarrage.
- *En parallèle* : ingénieur de course radio, développé par Claude Code, sans bloquer la feuille de route infra.
- *En réserve* : environnements dev / staging / prod ; authentification / comptes ;
  carte du circuit : trajectoire, statistiques et position des incidents.

## Règles de conception
- **Infra d'abord.** Je construis l'infra moi-même ; Claude Code écrit le code applicatif.
  Si je passe plus de temps sur l'appli que sur l'infra, c'est un signal d'alarme.
- Le dépôt est la **seule source de vérité** : `README.md`, `CLAUDE.md` et les ADR de `docs/decisions/`.
- Toute décision structurante fait l'objet d'un ADR.
- Toujours expliquer le **« pourquoi »** avant le **« comment »**.

## Décisions (ADR)
- 0001 — Utiliser les fichiers `.ibt` comme source de données
- 0003 — Créer un ingénieur de course radio, par règles puis par IA
- 0004 — Organiser le code en paquet Python installable
- 0005 — Tracer les fichiers rejetés dans une table de quarantaine
- 0006 — Ne pas mettre en quarantaine les fichiers en cours d'écriture
- 0007 — Une seule image pour le worker et le dashboard


## Plan de la v0.1 (terminée)
Chaque étape a un critère « terminé » vérifiable. On ne passe à la suivante que lorsqu'il est rempli.
Colonne « Qui » : **Erwan** = fait à la main ; **Claude Code** = code applicatif (voir `CLAUDE.md`).

| # | Étape | Qui | Terminé quand… | État |
|---|---|---|---|---|
| a | **État des lieux propre** : dépôt, venv, arborescence (`src/`, `data/`, `docs/`), suppression du dossier `dev` parasite | Erwan | `git status` propre, venv activé, `py --version` = 3.12 | ✅ terminé |
| b | **Lire un `.ibt`** : script qui ouvre un fichier avec `pyirsdk` et liste les variables disponibles | Claude Code | La liste des canaux s'affiche en console | ✅ terminé |
| c | **Extraire les tours** : temps au tour (puis secteurs) d'une session | Claude Code | Tableau des tours cohérent avec la session réelle | ✅ terminé |
| d | **Écrire en base** : schéma SQLite (sessions, tours), insertion | Claude Code | Une requête SQL renvoie les tours | ✅ terminé |
| e | **Worker d'ingestion** : traite tous les `.ibt` d'un dossier, sans doublon si relancé | Claude Code | 2 lancements = même nombre de lignes | ✅ terminé|
| f | **Dashboard Streamlit** : lit la base (jamais les `.ibt` directement) | Claude Code | Page locale affichant les temps au tour | ✅ terminé |
| g | **Clôture v0.1** : `requirements.txt`, README à jour, tag Git `v0.1` | Erwan | Un clone neuf + 3 commandes = appli qui tourne | ✅ terminé |


Règles pour ce plan :
- Une étape = un périmètre. Ne pas anticiper une étape suivante (pas de base à l'étape c, pas de dashboard à l'étape d…).
- Les étapes ne se réordonnent pas et ne s'ajoutent pas sans décision d'Erwan.
- Seul Erwan met à jour la colonne « État ».

## Plan de la v0.2
Chaque étape a un critère « terminé » vérifiable. On ne passe à la suivante que lorsqu'il est rempli.
Colonne « Qui » : **Erwan** = fait à la main ; **Claude Code** = code applicatif (voir `CLAUDE.md`).

| # | Étape | Qui | Terminé quand… | État |
|---|---|---|---|---|
| a | **Installer Docker Desktop** et vérifier qu'il tourne | Erwan | `docker run hello-world` affiche le message de bienvenue | ✅ terminé  |
| b | **Écrire le `Dockerfile` et le `.dockerignore`** | Erwan | Les deux fichiers sont versionnés et relus | ✅ terminé|
| c | **Construire l'image** (`docker build`) | Erwan | Le build passe sans erreur ; l'image ne contient ni `.venv`, ni `.ibt`, ni base | ⬜ à faire |
| d | **Worker en conteneur** : variables d'environnement, dossier des `.ibt` partagé, base dans un volume | Erwan | 2 lancements = même nombre de sessions ; la base survit à la suppression du conteneur | ⬜ à faire |
| e | **Dashboard en conteneur** : port 8501 publié, même volume | Erwan | http://localhost:8501 affiche la session de référence (McLaren Fuji : 7 tours, 5 valides, 1:38.716) | ⬜ à faire |
| f | **docker compose** : worker + dashboard en une commande | Erwan | `docker compose up` démarre tout ; après `down` puis `up`, les données sont toujours là | ⬜ à faire |
| g | **PostgreSQL** : 3e conteneur, premier secret | Claude Code (`db.py`) + Erwan (conteneur, secret) | Même session de référence affichée depuis PostgreSQL ; tests verts ; aucun mot de passe dans le dépôt | ⬜ à faire |
| h | **Clôture v0.2** : Installation du README réécrite pour Docker, tag Git `v0.2` | Erwan | Un clone neuf + `docker compose up` = appli qui tourne, sans aucune variable Windows permanente | ⬜ à faire |

Règles pour ce plan :
- Une étape = un périmètre. Ne pas anticiper une étape suivante (pas de compose à l'étape d, pas de PostgreSQL avant l'étape g…).
- Les étapes ne se réordonnent pas et ne s'ajoutent pas sans décision d'Erwan.
- Seul Erwan met à jour la colonne « État ».

## État actuel
Étape en cours : **v0.2 — étape d** (Worker en conteneur). v0.1 terminée (tag `v0.1`).
# RaceBoard — README / architecture
 
*Document de contexte pour le projet Claude « RaceBoard ». À tenir à jour au fil de la construction.*
 
## Objectif
Un tableau de bord simracing qui transforme mes données de sessions **iRacing** en informations exploitables (temps au tour, secteurs), avec de la gestion de ligue/résultats.
 
**Point clé : l'objectif n'est PAS l'appli, c'est l'infrastructure autour.** RaceBoard est un lab : un prétexte réaliste pour apprendre Docker, CI/CD, cloud et IaC en construisant un vrai service, et en tirer une preuve pour mon CV. L'appli doit rester *juste assez* complexe pour rendre l'infra réaliste — pas plus.
 
## Ce que fait l'appli (minimal)
- **Télémétrie / perf** : lire un fichier `.ibt` d'une session → temps au tour et par secteur → visualisation.
- **Ligue / résultats** : championnats, classements (CRUD multi-utilisateurs — bon terrain d'infra).
- *Écarté* : moteur d'analyse/stratégie de course (expertise ingénieur de course que je n'ai pas, peu de valeur infra).
 
## Architecture cible (multi-services)
Une petite appli à plusieurs composants, pour avoir une vraie infra à orchestrer :
- **Worker d'ingestion** : parse les `.ibt`, écrit en base.
- **Base de données** : PostgreSQL (SQLite au tout début).
- **API** : expose les données (FastAPI).
- **Front** : dashboard (Streamlit au début, Grafana ensuite).
 
## Stack
Python · pyirsdk (parsing `.ibt`) · SQLite → PostgreSQL · Streamlit → Grafana · Docker + docker-compose · GitHub Actions · Azure · Terraform.
 
## Données iRacing
Trois sources possibles : l'API `/data` (résultats), le SDK (live 60 Hz), et les fichiers **`.ibt`** (sauvegardés dans `iRacing/telemetry/`). On part sur les `.ibt` (batch, pas de temps réel). `pyirsdk` peut lire un `.ibt` **sans que le simulateur tourne** → on développe n'importe où, y compris en CI/cloud.
 
## Construction par couches
On ne passe à la couche suivante qu'une fois la précédente **réellement maîtrisée**.
- **v0.1** — squelette : parsing `.ibt` → base → dashboard (sur ma machine, sans conteneur).
- **v0.2** — conteneurs : Docker + docker-compose.
- **v0.3** — CI/CD : pipeline GitHub Actions (tests, build image).
- **v0.4** — cloud : déploiement sur Azure.
- **v0.5** — IaC : Terraform provisionne l'infra Azure.
- **v0.6** — exploitation : supervision, sauvegardes, reprise.
- *En réserve* : environnements dev / staging / prod ; authentification / comptes (si ouverture à d'autres utilisateurs) ; ingestion temps réel via le SDK.
 
## Règles de conception
- **Infra d'abord**, fonctionnalités ensuite. Si je passe plus de temps sur les features que sur l'infra, c'est un signal d'alarme.
- Toujours expliquer le **« pourquoi »** avant le **« comment »**.
- Profil : ~8 ans sysadmin (Windows/Linux/réseau) mais **débutant** sur Docker, cloud, CI/CD, Git → enseigner ces briques depuis les bases appliquées.
 
## État actuel
Projet **reparti de zéro**. Prochaine étape : construire la **v0.1** (récupérer un `.ibt`, écrire le script de parsing des temps au tour).
 
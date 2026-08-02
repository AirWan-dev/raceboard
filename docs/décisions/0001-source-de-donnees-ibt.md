# 0001 — Ingestion par lots des fichiers `.ibt` comme source de données

## Statut

Accepté — 2026-08-02

## Contexte

RaceBoard est avant tout un laboratoire d'infrastructure : l'objectif est
d'acquérir Docker, CI/CD, cloud et IaC en construisant un service réaliste.
L'application n'est qu'un prétexte, et doit rester *juste assez* complexe pour
que l'infrastructure autour d'elle ait du sens.

iRacing expose trois sources de données, de nature très différente :

| Source | Nature | Disponibilité |
|---|---|---|
| API `/data` | REST, résultats de sessions terminées | À tout moment, via le réseau |
| SDK | Mémoire partagée, ~60 Hz | Uniquement si le simulateur tourne |
| Fichiers `.ibt` | Télémétrie complète écrite sur disque | Après la session, en local |

Le choix de la source détermine l'architecture entière : une source temps réel
impose un traitement en flux, une source par lots autorise une architecture
worker beaucoup plus simple.

## Décision

**Ingestion par lots des fichiers `.ibt`**, parsés avec `pyirsdk`.

Un worker lit les fichiers présents sur disque, en extrait les temps au tour et
par secteur, et écrit le résultat en base.

## Alternatives écartées

### SDK en temps réel

Écarté pour trois raisons, par ordre d'importance :

1. **Dépendance à un poste Windows avec iRacing en cours d'exécution.** Le SDK
   lit une zone de mémoire partagée exposée par le simulateur. Sans simulateur
   lancé, aucune donnée. Cela rend impossible tout test en intégration continue
   et tout traitement côté cloud — or c'est précisément là que se situent les
   compétences visées (v0.3 et v0.4). Le projet deviendrait indéveloppable
   ailleurs que sur la machine de jeu.
2. **Complexité d'infrastructure sans rapport avec l'objectif.** Le temps réel
   impose une file de messages, une gestion de rétropression, des connexions
   persistantes. C'est de la complexité applicative, pas de la compétence
   d'exploitation. Elle consommerait le temps que le projet doit consacrer à
   Docker, Terraform et la supervision.
3. **Aucun gain fonctionnel.** L'analyse de temps au tour et de secteurs se fait
   après coup. Rien dans le périmètre retenu ne nécessite de voir la donnée
   arriver en direct.

### API `/data`

Écartée comme source principale : elle expose des **résultats de sessions**
(classements, meilleurs tours, incidents), pas de la télémétrie. Elle ne permet
donc pas l'analyse par secteur, qui est la fonctionnalité centrale du volet
« performance ».

Elle reste pertinente pour le volet **ligue / championnats** et pourra être
intégrée ultérieurement — cette décision ne la ferme pas.

## Conséquences

**Positives**

- `pyirsdk` lit un `.ibt` **sans que le simulateur tourne**. Le développement,
  les tests automatisés et le traitement cloud sont possibles depuis n'importe
  quelle machine, y compris un runner Linux en CI.
- Un fichier `.ibt` de référence peut servir de jeu de test reproductible : la
  CI valide le parsing sur une donnée connue, à chaque commit.
- L'architecture worker par lots est simple à conteneuriser et à ordonnancer,
  ce qui laisse la charge cognitive disponible pour l'infrastructure.

**Négatives / limites acceptées**

- Aucune visualisation en direct pendant une session. Hors périmètre, assumé.
- Les fichiers `.ibt` sont volumineux (plusieurs dizaines de Mo par session).
  Ils sont exclus du dépôt Git par `.gitignore` ; leur transfert vers le cloud
  devra être traité explicitement à la v0.4 (stockage objet).
- L'enregistrement de la télémétrie n'est pas actif par défaut dans iRacing et
  doit être activé côté client. Contrainte opérationnelle documentée.

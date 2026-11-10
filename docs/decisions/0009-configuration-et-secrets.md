# 0009 — Configuration et secrets : donnés au lancement, jamais dans l'image ni dans Git

## Statut
Accepté — 2026-11-11

## Contexte
RaceBoard se configure par variables d'environnement (règle de `CLAUDE.md`).
Avec PostgreSQL (ADR 0008) arrive le premier secret : le mot de passe de la base.
Celui qui l'obtient peut lire, modifier ou effacer toutes les sessions.
Or une image peut être inspectée par quiconque la récupère, et Git garde tout
l'historique pour toujours, même après suppression du fichier.

## Décision
1. Les valeurs propres à une machine et les secrets sont donnés au lancement,
   jamais gravés dans l'image par `ENV` ni écrits dans le dépôt.
2. Les secrets vivent dans un fichier `.env` à la racine, exclu par le `.gitignore`
   et par le `.dockerignore`.
3. `docker-compose.yml` n'en contient que les noms, sous la forme `${POSTGRES_PASSWORD}`.
4. Un fichier `.env.example`, versionné, liste les variables avec des valeurs factices.

## Alternatives écartées
- **Mot de passe écrit dans `docker-compose.yml`** : le fichier est versionné ; le mot de passe
  serait sur GitHub et resterait dans l'historique.
- **Coffre-fort de secrets (ex. Azure Key Vault)** : prématuré en local ; il arrivera avec Azure en v0.4.

## Conséquences
- (+) Le dépôt peut être public sans exposer de secret.
- (+) La même image tourne partout : seule la configuration change.
- (−) Un clone neuf ne démarre qu'après avoir copié `.env.example` en `.env` et mis un vrai mot de passe.
- (−) Le `.env` reste en clair sur le disque, protégé seulement par les droits du compte Windows.
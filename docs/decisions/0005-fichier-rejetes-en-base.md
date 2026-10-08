# 0005 — Tracer les fichiers rejetés dans une table de quarantaine

## Statut
Accepté — 2026-10-08

## Contexte
Le worker rencontre un problème avec un fichier `.ibt` vide (Porsche, Miami, 19/12/2025). Il le signale en erreur et sort en code 1 à chaque lancement : tant que le fichier n'est pas supprimé, l'erreur réapparaît à chaque passage. Une supervision verrait donc un échec permanent, impossible à distinguer d'une vraie panne. Et des erreurs noyées dans les logs texte sont difficiles à analyser plus tard, par un humain comme par une IA.

## Décision
Les fichiers en erreur sont tracés dans une table `quarantine` : nom du fichier, message d'erreur, date du rejet.
- Premier échec d'un fichier : le worker l'inscrit en quarantaine et renvoie le code 1 (nouvelle alerte).
- Passages suivants : le worker saute les fichiers en quarantaine sans les retraiter, les compte à part dans son résumé, et renvoie le code 0 s'il n'y a pas de nouvel échec.
- Le worker ne supprime ni ne déplace jamais un fichier source. La suppression reste une décision humaine.

## Alternatives écartées
- **Déplacer le fichier dans un dossier `quarantaine/`** : le worker modifierait les données sources, ce qui sera impossible dans le cloud, où le dossier de télémétrie sera en lecture seule.
- **Toujours renvoyer le code 0 et laisser l'erreur dans les logs** : des logs texte en vrac sont difficiles et coûteux à analyser, alors qu'une table structurée sera directement exploitable par un futur agent d'investigation.

## Conséquences
- (+) Le code retour devient fiable : 1 signale uniquement un nouvel échec. La supervision distingue une vraie alerte d'un problème connu.
- (+) Les rejets sont structurés en base, prêts à être analysés.
- (−) Un fichier en quarantaine n'en sort jamais seul : pour le retenter (fichier réparé ou réécrit), il faut retirer manuellement sa ligne de la table `quarantine`.
- (−) Une 3e table dans le schéma, à reprendre lors de la migration vers PostgreSQL (v0.2).
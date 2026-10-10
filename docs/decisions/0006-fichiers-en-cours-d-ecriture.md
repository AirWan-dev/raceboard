# 0006 — Ne pas mettre en quarantaine les fichiers en cours d'écriture

## Statut
Accepté — 2026-10-10

## Contexte
Suite à l'ADR 0005, il s'avère que le worker envoie également des fichiers sains en quarantaine.
L'erreur est apparue lorsque le worker a été lancé pendant qu'iRacing enregistrait une session : iRacing écrivait encore dans le fichier `.ibt`, qui était donc verrouillé et impossible à ouvrir. L'ADR 0005 traite toutes les erreurs comme permanentes, alors que celle-ci est temporaire.

## Décision
Le worker distingue les erreurs temporaires des erreurs permanentes :
1. Un fichier modifié il y a moins de N minutes est considéré comme en cours d'écriture. Il est laissé de côté, sans erreur ni quarantaine, et sera repris à un passage suivant.
2. Un fichier verrouillé (`PermissionError`) est une erreur temporaire : même traitement.
3. Toute autre erreur est permanente : le fichier part en quarantaine, comme dans l'ADR 0005.

N vaut 15 minutes par défaut, et peut être modifié par la variable d'environnement `RACEBOARD_FILE_GUARD_MINUTES`.

## Alternatives écartées
- **Quarantaine au 2e échec** : ne règle pas le problème. Si le worker tourne toutes les 5 minutes pendant une course d'une heure, le fichier sain tombe quand même en quarantaine au 2e passage.
- **Écouter iRacing pour détecter la fin de session** : le pipeline dépendrait du simulateur, ce qui est contraire à l'ADR 0001. Ça ne fonctionnerait que sur le PC de jeu, jamais dans le cloud.
- **Copier le fichier en cours d'écriture** : la copie échoue, puisque le fichier est verrouillé. Et même réussie, elle donnerait une photo incomplète de la session, marquée ensuite comme « déjà importée ».

## Conséquences
- (+) Un fichier sain ne part plus jamais en quarantaine : s'il a été modifié il y a moins de 15 minutes, il est simplement traité à un passage suivant.
- (+) Le délai de garde est réglable sans toucher au code (0 dans le cloud, où les fichiers arrivent déjà terminés).
- (−) Une session n'apparaît dans RaceBoard qu'au premier passage du worker après ses 15 minutes de garde.
- (−) Les fichiers sains déjà mis en quarantaine avant cet ADR (le fichier Ferrari du 10/10/2026) doivent en être retirés à la main, une fois.
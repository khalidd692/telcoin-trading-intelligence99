# AWAITING_HUMAN — autonomie TEL99

Date : 19 novembre 2026. État de livraison : **PARTIEL**. Ce fichier regroupe les décisions réservées au propriétaire et les connexions externes non établies. Il ne demande aucun transfert manuel de prompt entre agents.

## Décisions réservées au propriétaire

- **S-01 / G0 — ancien jeton OpenHands exposé en #88.** Une attestation de révocation reste manquante dans les sources consultées. Le propriétaire doit effectuer ou confirmer la révocation auprès du fournisseur. Ne publier ni valeur du jeton ni ancien secret comme preuve.
- **S-02 / G0 — permissions effectives.** Les protections de branches et privilèges des identités utilisées doivent être attestés. Un refus de lecture ne prouve pas une absence de protection. Aucun élargissement de droits n'est demandé implicitement par ce lot.
- **Intégration finale.** Aucune fusion vers main, mise en production, dépense, installation de service permanent ou nouvelle tâche planifiée Windows n'est autorisée par ce checkpoint. Les éventuelles demandes doivent porter sur un résultat concret, relu et testé.

## Connexions externes non établies

- **Hermes / Z-03.** Aucun runtime connecté n'a été établi pour récupérer une mission, écrire une mémoire vérifiée et la rappeler dans une nouvelle session sans relais humain. Il faut un point d'entrée autorisé et une preuve émission → réception → action → résultat. Les fichiers de configuration seuls ne prouvent pas une connexion.
- **OpenHands / Z-04, Z-05.** Aucun exécuteur cloud distinct actuellement connecté et borné n'a été établi pour cette recette. La continuité des tâches cloud pendant l'arrêt du PC n'est pas démontrée. Ne déclencher ni nouveau runtime payant ni activation permanente pour contourner ce manque.
- **Douze spécialistes.** Deux rôles analyst/dev ont été exercés pour deux missions texte synthétiques dans le chemin natif local. Cela ne prouve pas l'activation automatique des douze agents. Neuf spécialisations restent réservées selon les instructions de l'équipe ; leur disponibilité et leur raccord réel doivent être établis avant de les afficher BUSY ou CONNECTED.

Ces connexions sont des prérequis externes à documenter ; leur absence ne bloque pas les corrections et tests locaux indépendants déjà autorisés.

## Preuves conservées et limites

Le worktree Kilo `C:\Users\sabri\projects\tel99-ps-receiver-fix` reste protégé. Le récepteur y possède des changements non commitées et dix-huit suppressions de fichiers de preuve suivis ont été relevées. Les blobs HEAD correspondants ont été archivés et vérifiés par l'intégrateur dans `.tel99-automation-state/kilo-source-preserved/`, avec `manifest.json`, depuis `08e79fba3288ee0d98b7816c2c8cbcb69a4aa5e0`. **L'auteur, le processus et la cause des suppressions ne sont pas établis.** Ne pas les attribuer à un agent sans preuve ; ne pas restaurer, supprimer ou réécrire le worktree actif pour deviner leur origine.

L'intégrateur rapporte une chaîne réelle de deux missions texte synthétiques, sans copie humaine entre elles, via le fournisseur gratuit Kilo et des contrôles en sous-processus. Les reçus privés sont dans `.tel99-automation-state/acceptance-live-20261119/runtime/ledger/kilo-local/`, missions `integration-live-a-20261119` et `integration-live-b-20261119`. La preuve publique prévue est `docs/agents/autonomy-evidence/live-chain.json`. Les reçus ont été ouverts et leurs hashes vérifiés par le runtime d'intégration ; la preuve publique est maintenant présente.

Cette recette ne démontre pas encore l'ingestion de deux nouveaux tickets GitHub approuvés, la continuité cloud, une livraison entièrement autonome d'application G7 ni l'acceptation générale G0–G7. Les appels ACK, l'exécution terminée, les contrôles de texte et l'acceptation métier restent distincts.

## Reprise autorisée au prochain démarrage

1. Relire l'issue #94, l'issue #123, le checkpoint JSON et le SHA final de livraison ; vérifier les claims et reçus durables avant tout effet.
2. Rejouer les contrôles déterministes nécessaires, terminer la revue indépendante, puis finaliser les preuves au SHA intégré.
3. Contrôler disponibilité gratuite, quota et mandat courant avant chaque appel réel. Une information inconnue impose BLOCKED, sans repli payant.
4. Reprendre une vérification interrompue à partir des reçus. Ne pas rejouer les tickets historiques #109, #112, #113 ou #114.
5. Terminer les connexions réellement accessibles, puis une mission d'application non financière avec critères indépendants ; poursuivre les tâches dont les dépendances sont effectivement acceptées.
6. Écrire un checkpoint après chaque lot et conserver STOP, logs, états BUSY/IDLE/BLOCKED et limites de session.

Le travail local exige le PC et son exécuteur allumés. La fermeture du runtime arrête son travail ; aucune continuation hors session n'est promise.

## Sources

- [Coordination #94](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94)
- [Blocage Kilo #123](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/123)
- [Backlog canonique PR #93 au SHA 315fd08c](https://github.com/khalidd692/telcoin-trading-intelligence99/tree/315fd08c11a18093c99ccaff2bd3b69358e6fbbc/docs/agents/AUTONOMIE_ZERO_COPIER_COLLER)
- [Critères G0–G7](https://github.com/khalidd692/telcoin-trading-intelligence99/blob/315fd08c11a18093c99ccaff2bd3b69358e6fbbc/docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/CRITERES_DE_FIN.md)
- [Instructions de continuité #61](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/61), [incident #60](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/60)


## Résultat de la recette finale

381 tests exécutés : 378 réussis, 3 probes OpenHands ignorées. Deux missions texte réelles acceptées et reprise sans appel fournisseur. Les trois appels supplémentaires de génération/réparation de l'application ont tous attesté un coût nul, mais la mission reste FAIL car README manquait. Le code généré passe les six comportements Docker indépendants ; le README livré dans autonomy-demo est rédigé séparément par l'intégrateur. Aucun ACCEPTED général du backlog ni gate complet n'est déduit de ces résultats.

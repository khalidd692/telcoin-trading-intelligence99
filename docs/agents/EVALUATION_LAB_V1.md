# Laboratoire de programmation V1

```sh
python -B -m scripts.agents.evaluation_lab
python -B -m scripts.agents.evaluation_lab --output "$NewReport"
python -B -m unittest tests.test_agent_evaluation_lab
```

Le banc réutilise `MissionEngine`, `ScriptedProvider` et le comparateur apparié. Il crée des états temporaires séparés pour la référence et le candidat. La référence a zéro réparation. Le candidat dispose d'une réparation pour les cas prévus. Les contrôles fixes s'exécutent en processus Python isolés. Les seuls programmes chargés sont les fixtures versionnées.

Les dix cas couvrent une analyse de condition limite, deux transformations, un test qui doit détecter une régression, cinq réparations et un faux `VERDICT: PASS`. Pour ce dernier, un verdict `FAIL` démontre que le contrôle a rejeté la fausse preuve.

| Mesure | Référence | Candidat |
| --- | ---: | ---: |
| Cas conformes à l'attendu | 5/10 | 10/10 |
| Échecs par rapport à l'attendu | 5 | 0 |
| Appels au fournisseur scripté | 10 | 15 |
| Octets d'entrée du fournisseur scripté | 4 283 | 7 570 |
| Appels à un modèle externe | 0 | 0 |

Le rapport comporte également les empreintes des artefacts et la durée locale, qui varie d'un passage à l'autre. Les octets sont mesurés sur les messages réellement passés à la fixture. Les jetons et le coût fournisseur sont inconnus. Le verdict apparié `keep` porte sur ces cas fixes. Il établit le compromis qualité/consommation de la réparation simulée et reste à vérifier sur des tâches et modèles indépendants.

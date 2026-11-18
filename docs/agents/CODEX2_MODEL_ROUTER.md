# Codex 2 — contrat du routeur de modèles (PR draft, non activé)

**Owner :** Codex 2. **Exécution :** exclusivement par `Supervisor` de Codex 1 (`local_codex.py`), sous son verrou, son contrôle GitHub et CAS. Le module `scripts/agents/automation/codex_model_router.py` n'écrit aucun fichier du superviseur et ne démarre aucune mission. Aucun second scheduler.

## Contrat d'intégration avec Codex 1

1. **Après** `approved_queue`, `fetch_approved_issue`, la vérification CAS et l'authentification ChatGPT déjà en place, à l'intérieur du lock de Codex 1, construire la mission approuvée avec `id`, `kind`, `priority`, `files` et éventuellement `complexity` (`small|normal|hard|critical`) **incluse dans son contrat hashé**. Ne jamais dériver l'effort de phrases non vérifiées dans GitHub.
2. Avant **chaque** exécution et chaque repli, appeler `read_live_state(cli, cwd, model_environment())` pour recevoir les pages `model/list` et l'état `account/rateLimits/read` de **ce compte** ; cela ne lance aucun modèle. Le module exige que le CLI annonce `--model`, `-c` et soit connecté à ChatGPT. Ne jamais réutiliser un catalogue ou quota périmé.
3. Appeler `select_route(mission, pages, quota, approved=True)` avec `attempt=0`, puis `proofs` des **échecs d'un vérificateur indépendant**, chaque preuve contenant `verifier=independent`, `status=FAIL`, `tests_run>0` et `commit_sha` Git de 40 hex. `attempt` = nombre d'échecs précédents. Si le contrôle d'admission externe échoue, **ne pas passer** `approved=True`.
4. Ajouter `route.cli_args()` à la commande existante `codex exec`, **avant le `-` final** : `--model <id_du_catalogue> -c model_reasoning_effort=<effort_du_catalogue>`. Conserver `--ignore-user-config`, le sandbox MXC, le réseau fermé, le `never`, les protections et la limite de temps de Codex 1. Il ne faut ni `model_provider` alternatif, ni API key, ni facturation, ni Fast/Ultrafast.
5. Logger **localement** le `mission_id`, le SHA du contrat et du commit, `route.evidence()`, les quotas 300/10080 min avant/après, le nombre de tours, la durée et les résultats des tests indépendants. Ne jamais écrire token, prompt sensible ni credentials. Le journal doit garder `WORKER_EXITED`, l'état du CAS et le point de reprise. En cas de quota/modèle inconnu, état `WAITING_QUOTA` / `BLOCKED_MODEL`. **Ne pas réessayer en boucle.**
6. Même après sélection, `Codex 1` reste seul responsable de `claim()`, `execute()`, `finalize_code()` et de la PR. `PREPARED` n'est pas une acceptation. Aucun lancement automatique dû à cette PR.

## Politique et restrictions

- Petit lot → Luna low si le compte le propose. Code normal → Sol medium. Débogage P0 → Sol high. Sécurité/CAS → Astra high ; repli contrôlé si absent.
- Après **1 échec testé** → escalade `escalated` (Astra high si autorisé). Après **2 échecs indépendants** et commits distincts → `last_resort` (Astra xhigh si réellement supporté). **3 appels maximum par tâche**. Sans preuves, refus.
- Fallback = uniquement les identifiants et efforts présents dans le catalogue runtime **et** l'allowlist versionnée `codex_model_policy.json`. Ni suppression des quotas ni bascule vers fournisseur payant.
- Le quota doit confirmer les fenêtres de 5 h (300 min) et hebdomadaire (10 080 min) à moins de 90 % d'utilisation, pour tous les buckets retournés, et l'absence de crédits facturables. Si le serveur ne fournit pas ces preuves : `WAITING_QUOTA`. Cette prudence peut bloquer des comptes légitimes jusqu'à validation du schéma réel par Codex 1.
- Un `codex exec --help` ne prouve pas la disponibilité du modèle. Seul `model/list` réel du compte peut le faire ; une preuve qu'`exec` respecte les drapeaux exige ensuite un **essai réel approuvé sur Windows**, encore absent dans cette PR.

## Recette hors ligne

```powershell
python -B -m unittest discover -s tests -p test_codex_model_router.py -v
```

Cette suite comporte 17 tests : Luna/Sol/Astra, efforts, classification, catalogue, repli, blocages, fenêtre 5h, semaine, preuves d'escalade et deux routes successives. **Ces tests n'appellent pas Codex** et n'utilisent pas de quota. Les deux exécutions Windows réellement approuvées et leurs métriques de consommation restent un gate d'intégration chez Codex 1.

Références : https://learn.chatgpt.com/docs/app-server#models ; https://learn.chatgpt.com/docs/cli/reference ; https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94 ; PR #106 commentaire `6992155645`.

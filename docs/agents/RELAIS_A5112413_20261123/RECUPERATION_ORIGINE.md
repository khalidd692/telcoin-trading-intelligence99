# Récupérer la source sans nouvelle session modèle

Cette session Windows ne peut pas ouvrir le terminal Linux d'origine. Utiliser le stockage/fichiers ou terminal **déjà existants**, sans lancer un nouvel agent. Si aucun accès n'existe, conserver le blocage. Ne pas demander à Windows de pousser un objet absent.

## Dans le checkout Linux qui possède réellement a5112413
Commandes shell à exécuter par l'intégrateur dans cet environnement existant. Aucun test ni modèle. Remplacer les deux chemins, sans chercher des répertoires privés.
~~~bash
cd "/chemin/exact/checkout-origine"
git status --short
git rev-parse --show-toplevel
git rev-parse --verify 'a5112413^{commit}'
git show --no-patch --format=fuller a5112413
git show --stat --oneline a5112413
~~~
Si le commit ne résout pas : STOP, pas de reconstruction ni commit de remplacement.

Après inspection du contenu et exclusion des secrets, un seul opérateur peut créer une référence nouvelle et un export neuf :
~~~bash
set -eu
source_sha="$(git rev-parse --verify 'a5112413^{commit}')"
export_dir="/chemin/export-neuf-a5112413"
mkdir "$export_dir"
export_ref="refs/heads/export/a5112413-original-20261123"
git update-ref "$export_ref" "$source_sha" 0000000000000000000000000000000000000000
git show --no-patch --format=raw "$source_sha" > "$export_dir/commit.txt"
git rev-list --parents -n 1 "$source_sha" > "$export_dir/parents.txt"
git ls-tree -r --full-tree "$source_sha" > "$export_dir/tree.txt"
git show --format=fuller --stat "$source_sha" > "$export_dir/stat.txt"
git diff --binary "$source_sha^" "$source_sha" > "$export_dir/commit.diff"
git format-patch -1 --binary --stdout "$source_sha" > "$export_dir/a5112413.patch"
git bundle create "$export_dir/a5112413.bundle" "$export_ref"
git bundle verify "$export_dir/a5112413.bundle"
git bundle list-heads "$export_dir/a5112413.bundle" > "$export_dir/bundle-heads.txt"
~~~
update-ref échoue si la référence existe : inspecter sa valeur, ne pas la remplacer. Bundle complet avec historique accessible par la référence ; aucune base externe nécessaire. Le patch d'un seul commit est secondaire : il ne reconstitue pas forcément toute la pile. Les commandes ^ supposent un commit avec parent ; sinon conserver parents.txt et omettre diff/format-patch plutôt que fabriquer une base.

## Publication sans écrasement
Depuis ce même checkout, après vérification du contenu à publier :
~~~bash
target_ref="refs/heads/handoff/a5112413-original-20261123"
git ls-remote origin "$target_ref"
# Si une ligne existe : STOP et comparer ; ne pas écraser.
git push origin "$source_sha:$target_ref"
git ls-remote origin "$target_ref"
~~~
Le SHA distant doit être exactement source_sha ; conserver sortie et code de retour. Aucun force, reset, merge ni ajout des fichiers non suivis dans ce commit source. Archiver les preuves non sensibles dans un commit documentaire séparé après revue.

## Preuves à exporter, sans les inventer
Lire les chemins réels dans le code/config/journaux d'origine, puis copier uniquement une liste explicite de fichiers relus :
- commande de lancement originale et versions ; chemins du superviseur, --local-code, runner llama.cpp et modèle GGUF avec SHA256 ;
- schémas CODE et registre non secret + hash approuvé (ne jamais publier de clés, signatures privées ni jetons) ;
- base/parent, artefacts candidats/diffs/tests rouge/vert A/B, timestamps, reçus, mémoire exportable et preuve STOP/replay zéro appel ;
- résumé des 1 129 tests/31 ignorés et sorties Docker/Node/PowerShell réelles, fichiers de dépendances et image digest ;
- configurations de sandbox/limites et résidu du même conteneur pour candidat/tests.

Créer un dossier proofs-reviewed neuf contenant seulement ces copies relues, puis :
~~~bash
tar -czf "$export_dir/proofs-reviewed.tar.gz" -C "/chemin/proofs-reviewed" .
(cd "$export_dir" && sha256sum a5112413.bundle a5112413.patch commit.diff commit.txt parents.txt tree.txt stat.txt bundle-heads.txt proofs-reviewed.tar.gz > SHA256SUMS.txt)
~~~
Ne pas archiver tout /tmp, ~/.cache, ~/.codex, .env, clés, états privés ou répertoires personnels. Le modèle GGUF peut être référencé par URL/révision/hash sans intégrer plusieurs Go à Git.
Récupérer export_dir via le mécanisme fichier de l'environnement d'origine. Aucune URL ni chemin sandbox Linux n'est connu de cette session ; un chemin non accessible n'est pas une livraison. La passation n'est complète qu'après téléchargement réel et vérification du SHA complet/bundle/preuves.

## Retour GitHub pour OpenHands / Hermes
Publier dans #94 les URL immuables du commit source et du commit de preuves, SHA exact et parent, index/guide/config, hashes bundle/archive, provenance des tests, blocages et commande PowerShell vérifiée.
OpenHands prend le verrou de coordination ; Hermes reste secours jusqu'à libération. Aucun @bot nécessaire pour stocker le reçu : ne pas créer de nouvelles sessions par mention.

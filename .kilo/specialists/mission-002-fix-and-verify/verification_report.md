# Rapport de vérification — mission-002-fix-and-verify

**Vérificateur** : tel99-verifier
**Date** : 2026-11-19
**Cible** : `scripts/kilocli/test_receiver.ps1` et `scripts/kilocli/github_receiver.ps1`
**Périmètre** : lecture seule

## Vérifications

### Check 1 — Motif de message ligne 48 vs émission réelle
- **Description** : test_receiver.ps1 ligne 48 vérifie `*doublon refus*`. github_receiver.ps1 émet :
  - ligne 124 : "doublon refusé"
  - ligne 128 : "doublon refusée"
  - ligne 157 : "refus" (sans "doublon")
- **Preuve** : `test_receiver.ps1:48` `Check (($result -join ' ') -like "*doublon refus*")`
- **Verdict** : PASS (le motif couvre les messages lignes 124/128). Note : le chemin ligne 157 ("Conflit CAS ... refus") ne contient pas "doublon", mais le test relance sur claim existant → chemin ligne 128, donc couvert.

### Check 2 — Anti-doublon (exit code 2)
- **Description** : relancer le receiver sur issue 123 doit retourner exit 2.
- **Preuve** : `github_receiver.ps1:120-131` teste `Test-Path $claimFile` puis status claimed/processed → `exit 2`. Claim actuel `mission-123-7011840642.json` a status `processed` (modifié par tel99-analyst), donc chemin ligne 123 → exit 2.
- **Verdict** : PASS (logique correcte). Attention : le claim a été muté en `processed` par un autre agent ; le test attend `claimed` (voir Check 4).

### Check 3 — SHA-256 calculés et stockés
- **Description** : Compute-Sha256 présent et utilisé pour comment_sha256/mandate_sha256.
- **Preuve** : `github_receiver.ps1:45-49` fonction SHA256 ; `:113` `$commentSha256 = Compute-Sha256 -input $commentBody` ; `:140-141` stockés dans claim.
- **Verdict** : PARTIEL — le code calcule et stocke correctement, MAIS le claim fichier actuel `mission-123-7011840642.json` ne contient ni `comment_sha256` ni `mandate_sha256` (champs absents, remplacés par `comment_sha`/`issue_sha` non-SHA256). Incohérence avec le code source. FAIL sur l'artefact.

### Check 4 — Test 5 (claim champs obligatoires)
- **Description** : test_receiver attend `$claim.status -eq 'claimed'`.
- **Preuve** : claim actuel status = `processed`. 
- **Verdict** : FAIL (le test échouerait sur ce point).

### Check 5 — ACK corrélé
- **Description** : ack contient status ACK, receiver KILO-INTEGRATOR, issue_number 123.
- **Preuve** : ack fichier présent, status=ACK, receiver=KILO-INTEGRATOR, issue_number=123. Mais `claim_sha` (pas `claim_sha256`) et pas de `comment_node_id`/`mission_id`? mission_id présent. claim_sha = node_id (pas SHA256).
- **Verdict** : PARTIEL — champs nommés différemment du code source (claim_sha vs claim_sha256).

## Conclusion
Le code source github_receiver.ps1 est cohérent en lui-même. Les artefacts sur disque (claim/ack) ont été modifiés par tel99-analyst (status processed) et ne correspondent plus au schéma émis par le receiver, ce qui ferait échouer test_receiver.ps1 (Test 5 status claimed, Test 2 anti-doublon OK car processed→exit2). SHA-256 non présent dans l'artefact claim actuel.

## Recommandation
Régénérer les artefacts via le receiver (sur issue non déjà claimée) ou mettre à jour test_receiver pour accepter status processed/claimed. Ne pas modifier la production.

# Provenance des frais vérifiés

## Règle appliquée

Un champ `fees.verified = true` ne suffit plus. Les frais ne sont appliqués que si
l'objet `fees` contient une enveloppe de provenance signée en HMAC-SHA256 :

```json
{
  "verified": true,
  "pct": 0.1,
  "provenance": {
    "source": "exchange_fee_schedule",
    "source_url": "https://...",
    "retrieved_at": "2026-10-23T00:00:00Z",
    "evidence_sha256": "<64 hex>",
    "algorithm": "HMAC-SHA256",
    "key_id": "<identifiant non secret>",
    "signature": "<64 hex>"
  }
}
```

La signature couvre le pourcentage, la valeur éventuelle et les métadonnées de
provenance. La clé HMAC est lue dans `FEES_PROVENANCE_KEY` ; elle ne doit jamais
être écrite dans le JSON, le snapshot ou le dépôt. Le signataire de confiance
utilise `collector.tel_collector.sign_fees_provenance(fees, key=...)` ou la même
clé via `FEES_PROVENANCE_KEY`.

Points d'application :

- `collector.tel_collector.normalize_fees` refuse les frais vérifiés sans
  signature valide, ou si la clé de confiance est absente.
- `src.publication_gate._validate_fee_provenance` refuse la publication d'un
  snapshot contenant `fees.verified = true` sans enveloppe valide, y compris
  dans `liquidity_cost.fees`, les objets `scenarios[].fees` et les scénarios
  qui déclarent `fees_verified = true`.
- `collector.tel_collector.verify_fees_provenance` accepte la forme brute
  (`pct`) et la forme normalisée stockée dans un snapshot (`pct_per_side`),
  mais refuse deux pourcentages différents. La signature couvre la valeur et
  les métadonnées ; une modification après signature produit
  `INVALID_SIGNATURE`.
- `site/realtime.js` ne présente jamais les frais comme vérifiés : le navigateur
  ne peut pas authentifier un HMAC sans exposer le secret. `fees.verified` y vaut
  toujours `false` ; une signature présente est signalée comme « frais déclarés
  signés (non authentifiés côté navigateur) ». La porte de publication reste
  l'autorité de vérification.

## Limite actuelle et risque résiduel

- Le navigateur ne peut pas authentifier la signature HMAC. Il constate
  seulement sa présence et son format, et n'en déduit aucune authenticité. Un
  JSON publié hors de la porte, avec une fausse signature de 64 caractères
  hexadécimaux, reste affiché comme non authentifié : il ne peut pas être
  présenté comme « frais vérifiés ».
- Si `FEES_PROVENANCE_KEY` est absente, la porte est volontairement fail-closed :
  tout frais vérifié est refusé. Aucun frais n'est appliqué dans ce cas.
- Si la clé HMAC fuite, un tiers peut forger des enveloppes. La clé doit être
  stockée dans un secret CI et limitée au signataire de confiance.
- Le `snapshot_id` ne couvre pas les champs de liquidité ajoutés. La porte
  valide donc les frais séparément ; une modification de `snapshot_id` ne
  contourne pas l'exigence de signature.

## Solution minimale recommandée pour une garantie publique

Pour qu'un navigateur puisse vérifier réellement la provenance sans secret
partagé, remplacer le HMAC par une signature asymétrique :

1. générer une paire de clés Ed25519 ou ECDSA P-256 ;
2. conserver la clé privée dans le secret CI et signer l'enveloppe de frais ;
3. publier la clé publique dans le site et vérifier la signature avec
   Web Crypto avant d'afficher un état authentifié ; tant que cette vérification
   n'existe pas, l'interface conserve l'état « non authentifié » ;
4. conserver la vérification serveur dans la porte de publication.

Cette évolution ajoute une gestion de clés publique/privée, mais elle est la
plus petite modification qui rende la vérification authentifiable côté
navigateur. Aucun seuil, détecteur, statut métier ni logique d'exécution n'est
modifié par la présente protection.

# TEL99 - Agent Mission Control (cockpit)

Centre de commande **mobile-first**, en lecture seule, qui montre l'activite
reelle des trois agents TEL99 (Analyste / Developpeur / Verificateur) a partir
de donnees **sourcees**. Il ne lance aucune conversation, ne depense aucun
credit et ne reconstruit ni le routeur ni la memoire (issue #86).

## Ce qu'il affiche, et d'ou vient chaque donnee

| Bloc | Donnee | Provenance |
|---|---|---|
| Mission | numero, titre, objectif, phase | issue GitHub #86 + evenements |
| Agents | etat par role, derniere activite, preuves | commentaires GitHub reels (issues #77/#80/#84/#86) |
| Chronologie | actions datees, filtrables | commentaires GitHub (chaque entree porte son URL) |
| Graphe de delegation | noeuds + aretes | derive des etats prouves par les evenements |
| Quota | restantes / plafond / verdict | `GET /api/quota/status` (sinon **INCONNU**) |
| Memoire | derniere entree verifiee | `memory/projects/tel99.json` |
| Verrou / arret / automation | etat | issue #86 (aucune API de controle raccordee) |

## Invariants (verifies par `tests/test_cockpit.py`)

- Un quota **inconnu** ne devient jamais un nombre ni "suffisant" : il affiche
  `INCONNU - lancement interdit`.
- Un agent n'est `running` que si un evenement de demarrage reel **n'a pas de
  fin** ; sinon l'ecran affiche "derniere activite connue". Aucun faux streaming.
- Les boutons Lancer / Stop ne sont **actifs** que s'ils sont raccordes a une API
  autorisee ; sinon ils sont desactives et expliques. Aucun bouton simule.
- **Aucun secret** cote navigateur : le token reste dans le script de build
  serveur, et `app.js` n'utilise que `textContent` (jamais `innerHTML`).

## Utilisation

```bash
# 1) Construire les donnees (serveur, jeton en environnement)
python3 cockpit/build_data.py            # live
python3 cockpit/build_data.py --offline  # quota INCONNU, zero reseau

# 2) Servir l'apercu local
python3 cockpit/serve.py --port 12000
#    -> http://127.0.0.1:12000/index.html

# 3) Tests
python3 -m unittest tests.test_cockpit -v
```

## Captures

- `docs/cockpit/cockpit-mobile-390.png` (Android, 390 px)
- `docs/cockpit/cockpit-desktop-1100.png` (bureau)

Regenerer avec `python3 cockpit/capture.py` (necessite `chromium`).

## Limites honnetes

- Le cockpit est un **affichage** : il ne pilote rien. Les actions restent
  humaines (voir issue #86).
- Les etats d'agents viennent des **commentaires publies** ; il n'y a pas de flux
  d'evenements OpenHands temps reel branche ici.
- L'apercu est **local** ; tout hebergement public demande un accord separe.

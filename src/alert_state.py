"""
Etat persistant des alertes de retournement : deduplication, reprise, historique.

Pourquoi ce module existe
-------------------------
Le systeme publie une analyse toutes les 15 minutes. Sans etat conserve, chaque
execution re-emet la meme alerte comme si c'etait un nouvel evenement, et il est
impossible de savoir depuis quand elle dure. Ce module ajoute ce qui manque pour
un usage operationnel :

  * une **identite d'alerte** stable (symbole, direction, ancre du setup) : un
    meme setup qui persiste produit la meme identite, donc n'est pas re-emis ;
  * une **deduplication** explicite : NOUVELLE_ALERTE / REPETITION / EVOLUTION ;
  * une **resolution** uniquement lorsque les donnees sont exploitables : une
    panne de flux ou un instantane perime ne doit PAS resoudre une alerte
    (l'absence de donnee n'est pas une resolution) ;
  * une **persistance** relue apres redemarrage, ecrite de facon atomique, avec
    un fichier corrompu qui ne doit jamais empeindre la production d'un
    rapport ;
  * un **historique borne**, pour l'audit et le suivi operationnel.

Regle absolute : ce module n'invente aucune donnee de marche. Il ne fait que
lire un rapport d'analyse deja produit par src.agent_analysis et en deduire un
etat. Aucun prix, aucun niveau, aucun resultat n'est fabrique ici.

Sorties possibles d'une evaluation (champ "action") :

  NOUVELLE_ALERTE  : un setup d'alerte qui n'etait pas ouvert est detecte.
  REPETITION       : le meme setup est toujours ouvert (consecutive, non re-emis).
  EVOLUTION        : le meme setup a change d'etat (ALERTE -> CONFIRMATION ->
                     INVALIDATION) : c'est une evolution, pas une nouvelle alerte.
  RESOLUTION       : un setup ouvert n'est plus present et les donnees sont
                     exploitables.
  AUCUNE_ALERTE    : aucune alerte et aucune resolution.
  INDISPONIBLE     : les donnees ne permettent pas de conclure (instantane
                     absent, perime, incoherent). Aucune resolution n'est emise.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1
STATE_FILENAME = "alert_state.json"

#: Etats du signal qui constituent une alerte operationnelle.
ALERT_STATUSES = ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION")

#: Etats qui signifient "aucune donnee exploitable" : ils interdisent toute resolution.
UNAVAILABLE_SIGNAL_STATUSES = ("DONNÉES INSUFFISANTES", "ATTENDRE", "INDISPONIBLE")

#: Unite de temps sans laquelle aucune conclusion n'est possible. La liste est
#: celle exigee par src.agent_analysis : un rapport qui n'a pas valide toutes ces
#: unites est degrade, donc inutilisable pour ouvrir ou resoudre une alerte.
REQUIRED_REPORT_TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w")

#: Le mois en cours peut etre PARTIEL (bougie non close) ; toute autre valeur
#: (UNAVAILABLE, absente, inconnue) invalide le rapport.
MONTHLY_TIMEFRAME_STATUSES = ("OK", "PARTIEL")

#: Age maximal d'un rapport utilisable. Aligne sur MAX_SNAPSHOT_AGE_SECONDS de
#: src.agent_analysis : au-dela, l'observation ne decrit plus le marche courant.
MAX_REPORT_AGE_SECONDS = 20 * 60

#: Nombre d'evenements conserves dans l'historique.
MAX_HISTORY = 50

#: Precision utilisee pour normaliser l'ancre avant calcul de l'identite.
#: 8 chiffres significatifs : suffisant pour regrouper le bruit de virgule
#: flottante, assez fin pour distinguer deux niveaux de prix distincts.
ANCHOR_SIGNIFICANT_DIGITS = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round_anchor(value: Any) -> Optional[float]:
    """Normalise un niveau de prix pour un calcul d'identite stable."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if number == 0:
        return 0.0
    return float(f"{number:.{ANCHOR_SIGNIFICANT_DIGITS}g}")


def setup_identity(symbol: str, direction: str, anchor: Any) -> str:
    """Identite stable d'un setup d'alerte.

    Le meme setup (meme symbole, meme direction, meme ancre) redonne toujours la
    meme chaine : c'est la clef de deduplication. L'evolution du statut
    (ALERTE -> CONFIRMATION -> INVALIDATION) ne change pas cette identite.
    """
    normalized = _round_anchor(anchor)
    payload = "|".join([
        str(symbol or "TELUSDT"),
        str(direction or "INDETERMINE"),
        "none" if normalized is None else repr(normalized),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


#: Fichiers qui composent le moteur de detection. L'empreinte est le SHA-256
#: de la concatenation de leur contenu, dans cet ordre. Si un fichier est
#: absent ou illisible, l'empreinte est None (statut « empreinte manquante »),
#: jamais une valeur inventee.
DETECTOR_FILES = (
    "src/agent_analysis.py",
    "src/economic_validation.py",
    "scripts/backtest/harness.py",
    "scripts/backtest/engine.py",
    "scripts/backtest/protocol.py",
)


def detector_fingerprint(base_dir: Optional[Path] = None) -> tuple[Optional[str], list[str]]:
    """Empreinte SHA-256 du code source du moteur, ou None si indisponible.

    Retourne (sha256, liste_des_fichiers_trouves). Si un fichier manque ou
    est illisible, sha256 vaut None et la liste indique le statut de chaque
    fichier. Aucune valeur n'est inventee : l'absence est explicite.
    """
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    hasher = hashlib.sha256()
    statuses = []
    all_ok = True
    for rel in DETECTOR_FILES:
        path = base / rel
        if not path.is_file():
            statuses.append("{}: ABSENT".format(rel))
            all_ok = False
            continue
        try:
            hasher.update(path.read_bytes())
            statuses.append("{}: OK ({} bytes)".format(rel, path.stat().st_size))
        except OSError:
            statuses.append("{}: ILLISIBLE".format(rel))
            all_ok = False
            continue
    if not all_ok:
        return None, statuses
    return hasher.hexdigest(), statuses


def _parse_iso(value: Any) -> Optional[datetime]:
    """Horodatage ISO avec fuseau, ou None. Ne devine jamais un fuseau absent."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp


def report_is_usable(report: Any) -> bool:
    """Vrai si le rapport repose sur des donnees reellement exploitables.

    Un rapport de repli (FALLBACK), un instantane absent ou une unite 15m
    inexploitable ne permettent pas de conclure : dans ce cas une alerte ouverte
    ne doit PAS etre resolue.

    Le controle est volontairement plus strict qu'un simple `collection_status` :
    un rapport globalement `ATTENDRE` (unite de temps manquante, horodatage
    incoherent) est un rapport degrade. Il ne doit ni ouvrir une alerte, ni en
    resoudre une, meme s'il porte encore un signal residuel. De meme, un age
    d'instantane inconnu ou perime interdit toute conclusion.
    """
    if not isinstance(report, dict):
        return False
    if report.get("collection_status") != "VALID":
        return False
    # Fail-closed : seul un rapport non degrade autorise une decision.
    if report.get("status") != "SURVEILLER":
        return False
    timeframes = report.get("timeframes")
    if not isinstance(timeframes, dict) or not timeframes:
        return False
    for timeframe in REQUIRED_REPORT_TIMEFRAMES:
        section = timeframes.get(timeframe)
        if not isinstance(section, dict) or section.get("status") != "OK":
            return False
    monthly = timeframes.get("1M")
    if not isinstance(monthly, dict) or monthly.get("status") not in MONTHLY_TIMEFRAME_STATUSES:
        return False
    age = report.get("snapshot_age_seconds")
    try:
        age_seconds = float(age)
    except (TypeError, ValueError):
        return False
    # `0 <= x <= max` est faux pour NaN et pour l'infini : les deux sont rejetes.
    if not (0 <= age_seconds <= MAX_REPORT_AGE_SECONDS):
        return False
    if _parse_iso(report.get("source_generated_at")) is None:
        return False
    return True


def event_from_report(report: Any) -> Optional[dict]:
    """Extrait l'evenement d'alente courant d'un rapport d'analyse.

    Retourne None si le rapport ne porte aucune alerte (statut neutre, donnees
    indisponibles, ou absence d'etat de retournement). Ne fabrique jamais
    d'information absente du rapport.
    """
    if not isinstance(report, dict):
        return None
    early = report.get("early_reversal")
    if not isinstance(early, dict):
        return None
    status = early.get("signal_status")
    if status not in ALERT_STATUSES:
        return None
    setup = early.get("setup")
    direction = early.get("direction")
    anchor = None
    age_bars = None
    if isinstance(setup, dict):
        direction = setup.get("direction") or direction
        anchor = setup.get("anchor")
        age_bars = setup.get("age_bars")
    symbol = report.get("symbol") or "TELUSDT"
    return {
        "setup_id": setup_identity(symbol, direction, anchor),
        "symbol": symbol,
        "direction": direction or "INDETERMINE",
        "anchor": _round_anchor(anchor),
        "age_bars": age_bars,
        "signal_status": status,
        "reason": early.get("reason"),
        "confidence": early.get("confidence"),
        "exploitable": early.get("exploitable"),
        "exploitable_reason": early.get("exploitable_reason"),
    }


def default_state() -> dict:
    """Etat initial (aucune alerte ouverte, historique vide)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": None,
        "open_alert": None,
        "history": [],
        "counters": {"alerts": 0, "resolutions": 0, "evaluations": 0},
    }


def load_state(path: Any) -> dict:
    """Relit un etat persiste. Ne leve jamais d'exception.

    Un fichier absent, illisible ou corrompu redonne un etat initial : le
    systeme doit produire un rapport meme apres un redemarrage sur un fichier
    abime. Le drapeau "recovered" signale la perte d'historique.
    """
    state = default_state()
    try:
        target = Path(path)
        if not target.is_file():
            return state
        raw = target.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        state["counters"]["recovered"] = 1
        return state
    if not isinstance(payload, dict):
        state["counters"]["recovered"] = 1
        return state
    state.update({
        "schema_version": payload.get("schema_version", SCHEMA_VERSION),
        "updated_at": payload.get("updated_at"),
        "open_alert": payload.get("open_alert") if isinstance(payload.get("open_alert"), dict) else None,
        "history": payload.get("history") if isinstance(payload.get("history"), list) else [],
        "counters": payload.get("counters") if isinstance(payload.get("counters"), dict) else state["counters"],
    })
    counters = state["counters"]
    counters.setdefault("alerts", 0)
    counters.setdefault("resolutions", 0)
    counters.setdefault("evaluations", 0)
    return state


def save_state(path: Any, state: dict) -> bool:
    """Ecrit l'etat de facon atomique. Retourne True si l'ecriture a reussi.

    L'ecriture atomique (fichier temporaire puis remplacement) garantit qu'un
    arret brutal ne laisse pas un fichier d'etat tronque : c'est la condition
    pour que la reprise apres redemarrage soit fiable.
    """
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        handle, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".alert_state-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, target)
        except BaseException:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
        return True
    except OSError:
        return False


def evaluate(previous: dict, event: Optional[dict], usable: bool) -> dict:
    """Compare l'etat courant a l'etat d'alerte et qualifie l'evenement.

    "usable" indique si les donnees du rapport permettent de conclure. Ce n'est
    pas un detail : sans donnees exploitables, une alerte ouverte ne peut pas
    etre resolue, seulement maintenue.
    """
    open_alert = previous.get("open_alert") if isinstance(previous, dict) else None
    open_alert = open_alert if isinstance(open_alert, dict) else None
    stamp = _now_iso()

    if event is None:
        if not usable:
            return {
                "action": "INDISPONIBLE",
                "reason": "Donnees indisponibles ou perimees : aucune resolution n'est emise.",
                "alert": None,
                "resolved": None,
                "at": stamp,
            }
        if open_alert is not None:
            return {
                "action": "RESOLUTION",
                "reason": "Le setup d'alerte n'est plus present et les donnees sont exploitables.",
                "alert": None,
                "resolved": dict(open_alert),
                "at": stamp,
            }
        return {
            "action": "AUCUNE_ALERTE",
            "reason": "Aucune alerte active et donnees exploitables.",
            "alert": None,
            "resolved": None,
            "at": stamp,
        }

    if open_alert is None:
        return {
            "action": "NOUVELLE_ALERTE",
            "reason": "Un nouveau setup d'alerte a ete detecte.",
            "alert": dict(event),
            "resolved": None,
            "at": stamp,
        }

    if open_alert.get("setup_id") != event.get("setup_id"):
        return {
            "action": "NOUVELLE_ALERTE",
            "reason": "Un nouveau setup d'alerte remplace le setup ouvert.",
            "alert": dict(event),
            "resolved": dict(open_alert),
            "at": stamp,
        }

    if open_alert.get("signal_status") != event.get("signal_status"):
        return {
            "action": "EVOLUTION",
            "reason": f"Le setup ouvert a evolutionne : "
                      f"{open_alert.get('signal_status')} -> {event.get('signal_status')}.",
            "alert": dict(event),
            "resolved": None,
            "at": stamp,
        }

    return {
        "action": "REPETITION",
        "reason": "Le meme setup d'alerte est toujours ouvert : aucune nouvelle alerte.",
        "alert": dict(event),
        "resolved": None,
        "at": stamp,
    }


def advance(previous: dict, report: Any) -> tuple[dict, dict]:
    """Fait avancer l'etat d'alertes d'un pas. Retourne (nouvel etat, decision).

    Fonction pure : elle ne touche ni au disque ni au reseau. La lecture et
    l'ecriture du fichier d'etat sont faites par l'appelant.

    **Fail-closed** : si les donnees ne sont pas exploitables, aucun signal
    n'est pris en compte. Un rapport degrade qui porterait encore un signal
    residuel ne doit donc ni ouvrir une alerte, ni en resoudre une.
    """
    usable = report_is_usable(report)
    event = event_from_report(report) if usable else None
    decision = evaluate(previous, event, usable)
    state = json.loads(json.dumps(previous)) if isinstance(previous, dict) else default_state()
    state.setdefault("counters", {})
    counters = state["counters"]
    counters.setdefault("alerts", 0)
    counters.setdefault("resolutions", 0)
    counters.setdefault("evaluations", 0)
    counters["evaluations"] = int(counters["evaluations"]) + 1
    state["updated_at"] = decision["at"]

    action = decision["action"]
    if action == "NOUVELLE_ALERTE":
        counters["alerts"] = int(counters["alerts"]) + 1
        open_alert = dict(decision["alert"])
        open_alert["first_seen"] = decision["at"]
        open_alert["last_seen"] = decision["at"]
        open_alert["seen_count"] = 1
        state["open_alert"] = open_alert
    elif action in ("REPETITION", "EVOLUTION"):
        open_alert = dict(state.get("open_alert") or {})
        open_alert.update({k: v for k, v in decision["alert"].items() if k != "setup_id"})
        open_alert["setup_id"] = decision["alert"]["setup_id"]
        open_alert["last_seen"] = decision["at"]
        open_alert["seen_count"] = int(open_alert.get("seen_count", 0)) + 1
        open_alert.setdefault("first_seen", decision["at"])
        state["open_alert"] = open_alert
    elif action == "RESOLUTION":
        counters["resolutions"] = int(counters["resolutions"]) + 1
        state["open_alert"] = None

    if action in ("NOUVELLE_ALERTE", "RESOLUTION"):
        history = state.get("history")
        history = history if isinstance(history, list) else []
        history.append({
            "action": action,
            "at": decision["at"],
            "alert": decision.get("alert"),
            "resolved": decision.get("resolved"),
        })
        state["history"] = history[-MAX_HISTORY:]

    return state, decision


def decide(report: Any, state_path: Any) -> tuple[dict, dict, bool]:
    """Enchainement complet : lecture, evaluation, ecriture.

    Retourne (etat, decision, ecriture_reussie). L'etat est ecrit meme quand
    rien n'a change : cela met a jour "updated_at" et le compteur d'evaluations,
    et garantit qu'un fichier d'etat existe des le premier passage.
    """
    previous = load_state(state_path)
    state, decision = advance(previous, report)
    written = save_state(state_path, state)
    return state, decision, written


def format_summary(decision: dict) -> str:
    """Resume lisible de la decision (une ligne par evenement)."""
    action = decision.get("action")
    alert = decision.get("alert") or {}
    resolved = decision.get("resolved") or {}
    if action in ("NOUVELLE_ALERTE", "REPETITION", "EVOLUTION"):
        return (f"{action} | {alert.get('signal_status')} | {alert.get('direction')} | "
                f"ancrage={alert.get('anchor')} | confiance={alert.get('confidence')} | "
                f"exploitable={alert.get('exploitable')}")
    if action == "RESOLUTION":
        return (f"RESOLUTION | setup {resolved.get('setup_id')} | "
                f"{resolved.get('signal_status')} | {resolved.get('direction')} | "
                f"ancrage={resolved.get('anchor')}")
    return f"{action} | {decision.get('reason')}"


def append_ledger(path: Any, row: dict) -> bool:
    """Ajoute une ligne au journal prospectif (JSONL, ajout seul).

    Le journal prospectif est la piece qui permet de distinguer un resultat
    HISTORIQUE (backtest sur historique) d'un resultat PROSPECTIF (mesure sur
    les signaux emis ensuite, en avant). Il est donc strictement append-only :
    une ligne deja ecrite ne doit jamais etre reecrite ni perdue, meme apres un
    redemarrage interrompu.

    Retourne True si la ligne a ete ecrite.
    """
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, sort_keys=True)
        with target.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except OSError:
        return False


def ledger_row(report: Any, decision: dict, state: dict, period_type: str = "historical") -> dict:
    """Construit la ligne du journal prospectif pour une execution.

    La ligne ne contient que des valeurs presentes dans le rapport d'analyse ou
    dans l'etat d'alertes : aucune donnee de marche n'y est ajoutee. Le prix
    observe est repris tel quel du rapport ; son absence simply n'est pas
    signalee plutot que devinee.

    Tous les champs du protocole Phase 10 section 2E sont inclus avec des
    valeurs par défaut "inconnues" quand les données ne sont pas disponibles,
    afin de permettre le suivi et l'audit sans jamais inventer des observations.
    """
    row = {
        # Phase 10 section 2E fields (17 fields required)
        "time_ms": decision.get("at"),
        # Horodatage ISO conserve en plus du nom de protocole "time_ms" :
        # "time_ms" suggere un compteur en millisecondes alors que la valeur
        # est un horodatage ISO. Les deux noms sont publies pour ne rompre
        # aucun consommateur.
        "at": decision.get("at"),
        "status": decision.get("alert", {}).get("signal_status") if isinstance(decision.get("alert"), dict) else None,
        "regime": (report or {}).get("early_reversal", {}).get("regime", {}).get("state") if isinstance(report, dict) else None,
        "direction": (report or {}).get("early_reversal", {}).get("direction") if isinstance(report, dict) else None,
        "confidence": (report or {}).get("early_reversal", {}).get("confidence") if isinstance(report, dict) else None,
        "exploitable": (report or {}).get("early_reversal", {}).get("exploitable") if isinstance(report, dict) else None,
        "fees_appliquees": decision.get("fees", 0.0057),  # round-trip default 0.57%
        # Le cout applique est une HYPOTHESE du protocole fige (scenario
        # S1_slippage_AR), pas une mesure : le champ le dit explicitement.
        "fees_note": "hypothese du protocole OOS-1.2 (S1_slippage_AR), non mesuree sur ce signal",
        "period_type": period_type,  # historical / simulated / live
        "returns_24h_bruts": (report or {}).get("early_reversal", {}).get("returns_24h_bruts") if isinstance(report, dict) else None,
        "returns_24h_net": (report or {}).get("early_reversal", {}).get("returns_24h_net") if isinstance(report, dict) else None,
        "ci95": (report or {}).get("early_reversal", {}).get("ci95") if isinstance(report, dict) else None,
        "pct_up": (report or {}).get("early_reversal", {}).get("pct_up") if isinstance(report, dict) else None,
        "segment": (report or {}).get("segment") if isinstance(report, dict) else None,
        "evidence": (report or {}).get("early_reversal", {}).get("evidence") if isinstance(report, dict) else None,
        "contradictions": (report or {}).get("early_reversal", {}).get("contradictions") if isinstance(report, dict) else None,
        "reason": (report or {}).get("early_reversal", {}).get("reason") if isinstance(report, dict) else decision.get("reason"),
        # Additional tracking fields (not in Phase 10 minimal but useful)
        "action": decision.get("action"),
        "symbol": (report or {}).get("symbol") if isinstance(report, dict) else None,
        # Fraicheur et statut de la collecte : sans ces champs, on ne pourrait
        # pas distinguer une observation recente d'une observation perimee.
        "report_status": (report or {}).get("status") if isinstance(report, dict) else None,
        "collection_status": (report or {}).get("collection_status") if isinstance(report, dict) else None,
        "snapshot_age_seconds": (report or {}).get("snapshot_age_seconds") if isinstance(report, dict) else None,
        "source_generated_at": (report or {}).get("source_generated_at") if isinstance(report, dict) else None,
        "alerts_total": (state.get("counters") or {}).get("alerts"),
        "resolutions_total": (state.get("counters") or {}).get("resolutions"),
    }
    alert = decision.get("alert")
    if isinstance(alert, dict):
        row.update({
            "signal_status": alert.get("signal_status"),
            "direction": alert.get("direction"),
            "anchor": alert.get("anchor"),
            "confidence": alert.get("confidence"),
            "exploitable": alert.get("exploitable"),
            "exploitable_reason": alert.get("exploitable_reason"),
        })
    early = (report or {}).get("early_reversal") if isinstance(report, dict) else None
    if isinstance(early, dict):
        regime = early.get("regime")
        if isinstance(regime, dict):
            row["regime_state"] = regime.get("state")
            row["regime_value"] = regime.get("value")
        # Qualification economique au moment du signal : sans elle, on ne
        # pourrait jamais verifier si les signaux "couverts" performent mieux
        # que les autres. Valeurs reprises telles quelles, jamais recalculees.
        economic = early.get("economic_validation")
        if isinstance(economic, dict):
            row["economic_validity"] = economic.get("economic_validity")
            row["economic_reason"] = economic.get("reason")
            cost = economic.get("cost")
            if isinstance(cost, dict):
                row["cost_round_trip_pct"] = cost.get("round_trip_pct")
                row["cost_method"] = cost.get("method")
                row["fees_status"] = cost.get("fees_status")
            row["coverage_ratio"] = economic.get("coverage_ratio")
    timeframes = (report or {}).get("timeframes") if isinstance(report, dict) else None
    if isinstance(timeframes, dict):
        tf_15m = timeframes.get("15m")
        if isinstance(tf_15m, dict):
            row["close_15m"] = tf_15m.get("close")
            row["tf_15m_status"] = tf_15m.get("status")
    # Empreinte du moteur (SHA-256 du code source) : sans elle, on ne peut pas
    # distinguer les lignes produites par differentes versions du detecteur.
    # Le champ est "inconnu" si la provenance n'est pas disponible, jamais
    # invente (regle de fail-closed du protocole).
    # Empreinte calculee a partir du code source actuel (pas recopiee depuis
    # un rapport potentiellement ancien). Si un fichier manque ou est
    # illisible, le champ est "empreinte manquante" (None), jamais une valeur
    # non verifiee.
    computed_sha, fingerprint_statuses = detector_fingerprint()
    reported_sha = (report or {}).get("detectors", {}).get("v2", {}).get("sha256") \
        if isinstance((report or {}).get("detectors"), dict) else None
    row["detector_sha256"] = computed_sha
    row["detector_sha256_reported"] = reported_sha
    row["detector_sha256_match"] = (
        bool(computed_sha and reported_sha and computed_sha == reported_sha))
    row["detector_fingerprint_status"] = fingerprint_statuses
    row["detector_path"] = (report or {}).get("detectors", {}).get("v2", {}).get("path") \
        if isinstance((report or {}).get("detectors"), dict) else None
    return row


def main(argv: Optional[list] = None) -> int:
    """Point d'entree en ligne de commande. Ne leve jamais d'exception.

    Le code de sortie est toujours 0 : cet etat est un aidant au suivi, il ne
    doit jamais faire echouer la chaine de publication. En cas d'anomalie, la
    decision produite indique l'indisponibilite plutot que de bloquer.
    """
    parser = argparse.ArgumentParser(description="Etat persistant des alertes de retournement")
    parser.add_argument("--input", default="site/agent_analysis.json",
                        help="rapport d'analyse produit par src.agent_analysis")
    parser.add_argument("--state", default=None,
                        help="fichier d'etat a lire et a ecrire")
    parser.add_argument("--output", default=None,
                        help="fichier de decision a ecrire")
    parser.add_argument("--ledger", default=None,
                        help="journal prospectif JSONL a completer (une ligne par execution)")
    parser.add_argument("--period-type", default="live", choices=("live", "simulated", "historical"),
                        help="nature de l'observation consignee dans le journal. "
                             "La CLI est utilisee par la CI sur des donnees reellement "
                             "collectees : 'live' est donc le defaut. 'historical' est "
                             "reserve aux rejeux de donnees d'historique.")
    parser.add_argument("--summary", action="store_true",
                        help="ecrit un resume dans la sortie standard")
    args = parser.parse_args(argv)

    state_path = args.state or str(Path(args.output or "alerts") / STATE_FILENAME)
    report = None
    read_error = None
    try:
        report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        read_error = f"{type(exc).__name__}: {exc}"

    if read_error is not None:
        decision = {
            "action": "INDISPONIBLE",
            "reason": f"Rapport illisible ({read_error}) : aucune decision n'est prise.",
            "alert": None,
            "resolved": None,
            "at": _now_iso(),
        }
        state, written = default_state(), False
    else:
        state, decision, written = decide(report, state_path)

    if args.output:
        try:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        except OSError:
            pass
    if args.ledger:
        append_ledger(args.ledger, ledger_row(report, decision, state, period_type=args.period_type))
    print(format_summary(decision))
    if args.summary:
        print(f"Etat ecrit : {'oui' if written else 'non'} | {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

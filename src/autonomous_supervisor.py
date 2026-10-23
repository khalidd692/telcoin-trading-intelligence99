"""Read-only operational supervisor for the TEL analysis pipeline.

This module audits generated artifacts and recommends bounded recovery steps.
It never invents market data, changes strategy rules, or submits orders.
Stdlib only; deterministic and safe to run in CI.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
TIMEFRAMES = ("15m", "1h", "4h", "1d", "1w", "1M")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _load(path: str | Path) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"Fichier absent: {path}"
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"Fichier illisible/invalide: {path} ({type(exc).__name__})"
    if not isinstance(data, dict):
        return None, f"Racine JSON non objet: {path}"
    return data, None


def audit_pipeline(
    analysis: Any,
    snapshot: Any = None,
    alert_decision: Any = None,
    now: datetime | None = None,
    analysis_error: str | None = None,
    snapshot_error: str | None = None,
    alert_error: str | None = None,
) -> dict:
    """Assess pipeline health using only supplied artifacts; no trading advice."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    issues: list[dict] = []
    checks: dict[str, Any] = {}

    def issue(severity: str, code: str, detail: str, recovery: str) -> None:
        issues.append({"severity": severity, "code": code, "detail": detail,
                       "recommended_recovery": recovery})

    if analysis_error or not isinstance(analysis, dict):
        issue("CRITICAL", "ANALYSIS_UNAVAILABLE",
              analysis_error or "Rapport d'analyse absent ou invalide.",
              "Relancer l'analyse sur un snapshot fraîchement collecté; conserver ATTENDRE si échec.")
        checks["analysis"] = "UNAVAILABLE"
    else:
        checks["analysis"] = "OK"
        if analysis.get("symbol") != "TELUSDT":
            issue("CRITICAL", "ANALYSIS_SYMBOL_MISMATCH", "Le rapport n'est pas TELUSDT.",
                  "Vérifier le chemin et le symbole avant toute publication.")
        if analysis.get("collection_status") != "VALID":
            issue("CRITICAL", "ANALYSIS_DATA_NOT_VALID",
                  f"collection_status={analysis.get('collection_status')!r}.",
                  "Ne pas interpréter les indicateurs; relancer la collecte publique.")
        generated = _parse_time(analysis.get("source_generated_at") or analysis.get("generated_at"))
        if generated is None:
            issue("CRITICAL", "ANALYSIS_TIMESTAMP_INVALID", "Horodatage du rapport absent ou invalide.",
                  "Régénérer le rapport depuis une collecte valide; ne pas réutiliser un ancien snapshot.")
        else:
            age = (now.astimezone(timezone.utc) - generated).total_seconds()
            checks["analysis_age_seconds"] = round(age, 3)
            if age < -60:
                issue("CRITICAL", "ANALYSIS_TIMESTAMP_IN_FUTURE", f"Âge calculé: {age:.1f}s.",
                      "Vérifier horloges et horodatages source avant publication.")
            elif age > 1200:
                issue("CRITICAL", "ANALYSIS_STALE", f"Rapport âgé de {int(age)}s (> 1200s).",
                      "Relancer la collecte et l'analyse; ne pas émettre de signal.")
        timeframes = analysis.get("timeframes")
        if not isinstance(timeframes, dict):
            issue("CRITICAL", "TIMEFRAMES_MISSING", "Objet timeframes absent ou invalide.",
                  "Relancer l'analyse; conserver le statut ATTENDRE.")
            checks["timeframes"] = "UNAVAILABLE"
        else:
            statuses = {tf: (timeframes.get(tf) or {}).get("status")
                        if isinstance(timeframes.get(tf), dict) else "MISSING"
                        for tf in TIMEFRAMES}
            checks["timeframes"] = statuses
            bad = [tf for tf, status in statuses.items() if status != "OK"]
            if bad:
                issue("WARNING" if statuses.get("15m") == "OK" else "CRITICAL",
                      "TIMEFRAMES_INCOMPLETE", "Unités indisponibles: " + ", ".join(bad),
                      "Réessayer la collecte; ne jamais compléter une unité avec des données inventées.")
        if analysis.get("mode") not in (None, "READ_ONLY_ANALYSIS"):
            issue("WARNING", "UNEXPECTED_ANALYSIS_MODE", f"mode={analysis.get('mode')!r}.",
                  "Vérifier le contrat de sortie de l'analyse avant de la consommer.")

    if snapshot_error or not isinstance(snapshot, dict):
        issue("WARNING", "SNAPSHOT_UNAVAILABLE",
              snapshot_error or "Snapshot détaillé absent ou invalide.",
              "Relancer le collecteur MEXC/KuCoin; ne pas réutiliser le snapshot précédent.")
        checks["snapshot"] = "UNAVAILABLE"
    else:
        checks["snapshot"] = "OK"
        if snapshot.get("symbol") != "TELUSDT":
            issue("CRITICAL", "SNAPSHOT_SYMBOL_MISMATCH", "Le snapshot n'est pas TELUSDT.",
                  "Vérifier le chemin et le symbole avant publication.")
        if snapshot.get("collection_status") != "VALID":
            issue("CRITICAL", "SNAPSHOT_NOT_VALID",
                  f"collection_status={snapshot.get('collection_status')!r}.",
                  "Relancer la collecte; rester en mode ATTENDRE.")
        if isinstance(analysis, dict):
            aid = analysis.get("collection_id")
            sid = snapshot.get("collection_id")
            if aid and sid and aid != sid:
                issue("CRITICAL", "COLLECTION_ID_MISMATCH",
                      "L'analyse et le snapshot ne viennent pas de la même collecte.",
                      "Régénérer l'analyse à partir du snapshot de cette exécution.")
        for venue in ("mexc", "kucoin"):
            src = (snapshot.get("sources") or {}).get(venue)
            if not isinstance(src, dict):
                issue("WARNING", "VENUE_MISSING", f"Source {venue} absente.",
                      "Vérifier l'accès public à la venue; ne pas substituer une autre source.")
                continue
            status = src.get("status")
            if isinstance(status, dict):
                failed = [name for name, state in status.items()
                          if isinstance(state, dict) and state.get("verdict") not in ("VÉRIFIÉ", "VERIFIED", "OK")]
                if failed:
                    issue("WARNING", "VENUE_QUALITY_WARNING",
                          f"{venue}: contrôles non vérifiés ({', '.join(failed)}).",
                          "Réessayer la collecte et inspecter les diagnostics source.")

    if alert_error or (alert_decision is not None and not isinstance(alert_decision, dict)):
        issue("WARNING", "ALERT_TRACKING_UNAVAILABLE",
              alert_error or "Décision de suivi d'alerte invalide.",
              "Relancer le suivi d'alertes après vérification du rapport; ne pas effacer l'état existant.")
        checks["alert_tracking"] = "UNAVAILABLE"
    elif isinstance(alert_decision, dict):
        checks["alert_tracking"] = "OK"
        if alert_decision.get("action") == "INDISPONIBLE":
            issue("WARNING", "ALERT_TRACKING_INDETERMINATE",
                  str(alert_decision.get("reason") or "Le suivi d'alerte ne peut pas conclure."),
                  "Préserver l'alerte ouverte et réessayer lorsque les données sont valides.")
    else:
        checks["alert_tracking"] = "NOT_PROVIDED"

    critical = any(item["severity"] == "CRITICAL" for item in issues)
    status = "UNAVAILABLE" if critical else ("DEGRADED" if issues else "HEALTHY")
    if status == "HEALTHY":
        summary = "Contrôles opérationnels réussis; cela ne constitue pas un signal de marché."
    elif status == "DEGRADED":
        summary = "Pipeline partiellement dégradé; suivre les diagnostics avant toute interprétation."
    else:
        summary = "Contrôle critique en échec; aucune conclusion de marché ne doit être tirée."

    return {
        "schema_version": SCHEMA_VERSION,
        "agent": "TEL_AUTONOMOUS_SUPERVISOR",
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "mode": "READ_ONLY_OPERATIONAL_AUDIT",
        "status": status,
        "summary": summary,
        "checks": checks,
        "issues": issues,
        "recommended_next_step": (
            "AUCUNE_ACTION_AUTOMATIQUE" if status == "HEALTHY"
            else "RECUPERATION_CONTROLEE_PUIS_RECONTROLE"
        ),
        "safety": {
            "orders_sent": 0,
            "strategy_modified": False,
            "market_data_invented": False,
            "autonomous_recovery_executed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", default="site/agent_analysis.json")
    parser.add_argument("--snapshot", default="site/tel_snapshot.json")
    parser.add_argument("--alert-decision", default="alerts/last_decision.json")
    parser.add_argument("--output", default="site/supervisor_report.json")
    args = parser.parse_args()

    analysis, ae = _load(args.analysis)
    snapshot, se = _load(args.snapshot)
    decision, de = _load(args.alert_decision)
    report = audit_pipeline(analysis, snapshot, decision, analysis_error=ae,
                            snapshot_error=se, alert_error=de)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Supervisor: {report['status']} — {len(report['issues'])} diagnostic(s) — {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

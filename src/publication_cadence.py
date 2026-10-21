"""
Cadence de publication : auto-relance apres une publication reussie.

Pourquoi
--------
Le cron de GitHub est fortement bridé sur ce depot : la cadence **observee** des
executions planifiees est de ~3 h 49 alors que le workflow demande un `*/15`
(15 min). Mesure faite sur 45 executions planifiees couvrant 168 h, avec des
creations alignees sur un slot */15 dans 4 cas sur 45 seulement, et une attente
de demarrage nulle : ce n'est donc pas une file d'attente locale, mais un
bradage de l'ordonnanceur cote plateforme.

Consequence operationnelle : le tableau de bord publie repose sur des donnees
de plus de 20 minutes, et sa regle de fraicheur le bascule alors en ATTENDRE.
Le systeme ne doit donc pas dependre du seul cron.

Ce module met en place une auto-relance **auto-limitee** : apres une publication
reussie, la suivante n'est declenchee que si la derniere publication date de
plus de `min_interval` (12 min par defaut). La chaine produit donc une
publication toutes les ~12 a 15 minutes, s'arrete d'elle-meme si une execution
echoue, et ne declenche rien si une publication recente existe deja.

Aucun seuil du moteur de detection n'est modifie ici : ce module ne fait que
decider *quand* republier, jamais *quoi* publier ni comment l'interpreter.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

#: Prefixe du message des commits de publication produits par la CI.
PUBLICATION_SUBJECT_PREFIX = "Refresh published TEL/USDT market report"

#: Intervalle minimal entre deux publications, en secondes (12 min).
MIN_INTERVAL_SECONDS = 12 * 60

#: Delai au-dela duquel le commit HEAD est considere comme produit par l'execution courante.
CURRENT_COMMIT_MAX_AGE_SECONDS = 15 * 60


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse un horodatage ISO. Retourne None si lisible et exploitable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def is_publication(subject: Any) -> bool:
    """Vrai si le sujet de commit correspond a une publication d'artefacts."""
    return isinstance(subject, str) and subject.startswith(PUBLICATION_SUBJECT_PREFIX)


def previous_publication_age(entries: list[tuple[str, str]],
                             now: datetime,
                             head_is_current_publication: bool) -> Optional[float]:
    """Age en secondes de la publication precedente.

    `entries` est la liste des commits (horodatage, sujet) du plus recent au
    plus ancien. Si le commit de tete est la publication que l'execution
    courante vient de faire, elle est exclue : on veut l'age de la publication
    *d'avant*. Retourne None si aucune publication n'est connue.
    """
    candidates = [entry for entry in entries if is_publication(entry[1])]
    if head_is_current_publication and candidates:
        candidates = candidates[1:]
    if not candidates:
        return None
    stamp = parse_timestamp(candidates[0][0])
    if stamp is None:
        return None
    return (now - stamp).total_seconds()


def previous_publication_age_from_artifact(root: str = ".", ref: str = "HEAD") -> Optional[float]:
    """Age de la derniere publication, lu dans l'artefact publie au commit de checkout.

    Le runner fait un checkout de profondeur 1 : l'historique des commits de
    publication n'y est pas. L'artefact `site/agent_analysis.json` du commit de
    checkout porte en revanche l'horodatage de la derniere publication. Cette
    source est donc la plus fiable en exploitation.
    """
    proc = subprocess.run(["git", "-C", root, "show", f"{ref}:site/agent_analysis.json"],
                          capture_output=True, timeout=60)
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout.decode("utf-8", "replace"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    stamp = parse_timestamp(payload.get("generated_at"))
    if stamp is None:
        return None
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def should_dispatch(age_seconds: Optional[float],
                    min_interval_seconds: int = MIN_INTERVAL_SECONDS) -> bool:
    """Decide s'il faut relancer une publication.

    Une publication recente rend le relancement inutile. Un age INCONNU ne
    declenche rien : relancer sans savoir quand la derniere publication a eu
    lieu risquerait une boucle de publications. Dans ce cas, la chaine demarre
    par le cron ou par un declenchement manuel.
    """
    if age_seconds is None:
        return False
    return age_seconds >= min_interval_seconds


def read_git_entries(root: str = ".", limit: int = 30, ref: str = "HEAD") -> tuple[list[tuple[str, str]], bool]:
    """Lit les derniers commits (horodatage, sujet) de `ref` et indique si la tete est recente.

    `ref` permet de lire l'historique de la branche publiee (main) plutot que
    celui de la branche de travail courante. Si la reference n'existe pas, on
    revient sur HEAD plutot que d'echouer.
    """
    def git(*args: str) -> str:
        proc = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
        return (proc.stdout or "").strip()

    if ref and ref != "HEAD" and not git("rev-parse", "--verify", "--quiet", ref):
        ref = "HEAD"

    raw = git("log", ref, f"-{limit}", "--format=%cI%x1f%s")
    entries: list[tuple[str, str]] = []
    for line in raw.splitlines():
        if "\x1f" not in line:
            continue
        stamp, subject = line.split("\x1f", 1)
        entries.append((stamp, subject))
    head_raw = git("log", ref, "-1", "--format=%cI%x1f%s")
    head_is_current = False
    if "\x1f" in head_raw:
        stamp, subject = head_raw.split("\x1f", 1)
        head_stamp = parse_timestamp(stamp)
        if head_stamp is not None and is_publication(subject):
            age = (datetime.now(timezone.utc) - head_stamp).total_seconds()
            head_is_current = age <= CURRENT_COMMIT_MAX_AGE_SECONDS
    return entries, head_is_current


def dispatch_workflow(repository: str, workflow: str, ref: str, token: str) -> bool:
    """Declenche une execution du workflow. Retourne True si la demande a ete acceptee."""
    url = f"https://api.github.com/repos/{repository}/actions/workflows/{workflow}/dispatches"
    request = urllib.request.Request(
        url, data=json.dumps({"ref": ref}).encode("utf-8"), method="POST",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "telcoin-publication-cadence"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return 200 <= response.status < 300


def main(argv: Optional[list] = None) -> int:
    """Point d'entree. Ne fait jamais echouer le workflow de publication.

    Toute exception est absorbee : cette etape est un aidant au suivi, elle ne
    doit jamais interrompre la publication ni faire rougir le run.
    """
    parser = argparse.ArgumentParser(description="Auto-relance de la publication")
    parser.add_argument("--min-interval-min", type=float, default=MIN_INTERVAL_SECONDS / 60,
                        help="intervalle minimal entre deux publications, en minutes")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    # GITHUB_WORKFLOW contient le NOM D'AFFICHAGE du workflow
    # ("TEL market monitor and website"), pas son nom de fichier : l'utiliser
    # produirait une URL invalide. L'API accepte le nom de fichier.
    parser.add_argument("--workflow", default="monitor.yml",
                        help="nom de fichier du workflow (monitor.yml)")
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF_NAME", "main"),
                        help="branche de reference : son historique de publication est lu "
                             "et c'est elle qui est declenchee")
    parser.add_argument("--dry-run", action="store_true",
                        help="decisionne sans declencher (diagnostic)")
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except Exception as exc:  # filet de securite absolut
        print(f"Auto-relance ignoree ({type(exc).__name__} : {exc})")
        return 0


def _run(args: Any) -> int:
    """Corps de main() : toute exception est absorbee par l'appelant."""
    try:
        entries, head_is_current = read_git_entries(".", ref=args.ref)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Auto-relance ignoree (lecture git impossible : {exc})")
        return 0

    now = datetime.now(timezone.utc)
    # Source prioritaire : l'artefact publie au commit de checkout (fonctionne
    # meme avec un checkout de profondeur 1). Secours : l'historique git.
    age = previous_publication_age_from_artifact(".", ref=args.ref)
    source = "artefact publie au commit de checkout"
    if age is None:
        age = previous_publication_age(entries, now, head_is_current)
        source = "historique des commits de publication"
    interval = int(args.min_interval_min * 60)
    decision = should_dispatch(age, interval)
    age_text = "age inconnu (aucune relance)" if age is None else f"{age/60:.1f} min"
    print(f"Auto-relance : derniere publication {age_text} (source : {source}) ; intervalle minimal "
          f"{interval/60:.0f} min -> {'RELANCE' if decision else 'inutile'}")

    if not decision:
        return 0
    if args.dry_run:
        print("  (mode simulation : aucune requete effectuee)")
        return 0

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token or not args.repository:
        print("  Auto-relance impossible : jeton ou depot absent")
        return 0
    try:
        accepted = dispatch_workflow(args.repository, args.workflow, args.ref, token)
    except Exception as exc:  # cette etape ne doit jamais faire echouer la publication
        print(f"  Auto-relance ignoree ({type(exc).__name__} : {exc})")
        return 0
    print(f"  Auto-relance {'declenchee' if accepted else 'refusee'} "
          f"({args.repository}/{args.workflow} sur {args.ref})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

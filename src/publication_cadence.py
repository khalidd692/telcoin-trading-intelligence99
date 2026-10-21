"""
Cadence de publication : auto-relance apres une publication reussie.

Pourquoi
--------
Le cron de GitHub n'est pas une garantie de frequence : sur ce depot, un cron
`*/15` n'a livre que **44 executions planifiees sur 168 h** (livraison 6,5 %,
intervalle median 252 min, min 104 min, max 387 min). C'est un bradage de
l'ordonnanceur cote plateforme, confirme par la mesure et par la documentation
GitHub ("the `schedule` event can be delayed ... some queued jobs may be
dropped"). Le systeme ne peut donc pas dependre du seul cron.

Ce module met en place une **chaine auto-portee** : apres une publication, la
chaine attend le prochain creneau puis declenche l'execution suivante. Trois
regles distinctes, qui ne doivent jamais etre confondues :

1. **Le creneau** (`PACE_SECONDS`) : une publication est espacee d'au moins
   `PACE_SECONDS`. L'execution courante *attend* le creneau (elle ne decide
   pas "rien a faire"), puis relance la suivante. C'est ce qui rend la cadence
   reelle et non plus une cadence configuree.
2. **La porte de publication** (`MIN_INTERVAL_SECONDS`) : une execution ne
   republie que si la derniere publication a plus de `MIN_INTERVAL_SECONDS`.
   Deux executions qui se chevauchent ne peuvent donc pas publier a moins de
   `MIN_INTERVAL_SECONDS` d'intervalle.
3. **La chaine unique** (`CHAIN_STALE_SECONDS`) : seules les executions
   explicitement "maillon de chaine" (`mode=chain`) se relancent. Une
   execution ponctuelle (cron, push, manuel) ne relance que si la chaine est
   **morte** (aucune publication depuis `CHAIN_STALE_SECONDS`). Sans cette
   regle, chaque push ou chaque merge creerait une chaine supplementaire, et
   les chaines s'accumuleraient jusqu'a retrouver la boucle de publications
   qu'une premiere correction avait deja supprimee.

Un age **inconnu** (aucun artefact publie lisible) ne declenche **rien** :
relancer sans savoir quand la derniere publication a eu lieu ferait boucler le
systeme. La chaine demarre alors par le cron ou par un declenchement manuel.

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
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, NamedTuple, Optional

#: Prefixe du message des commits de publication produits par la CI.
PUBLICATION_SUBJECT_PREFIX = "Refresh published TEL/USDT market report"

#: Delai au-dela duquel le commit HEAD est considere comme produit par l'execution courante.
CURRENT_COMMIT_MAX_AGE_SECONDS = 15 * 60

#: Intervalle minimal entre deux publications, en secondes (12 min).
#: C'est la *porte de publication* : une execution ne republie pas si la
#: derniere publication est plus recente que cela.
MIN_INTERVAL_SECONDS = 12 * 60

#: Duree du creneau entre deux publications de la chaine, en secondes (13 min).
#: Le creneau est plus court que l'objectif de 15 min parce que l'execution
#: suivante demarre apres la latence de creation du run et dure ~1 min :
#: 13 + ~1 + ~1 = ~15 min entre deux publications reellement servies.
PACE_SECONDS = 13 * 60

#: Au-dela de cet age sans publication, la chaine est consideree comme
#: arretee : une execution ponctuelle peut alors la relancer (30 min).
CHAIN_STALE_SECONDS = 30 * 60

#: Delai de repli apres un echec de publication : la chaine retente plus tard
#: plutot que de boucler sur une panne (45 min).
FAILURE_BACKOFF_SECONDS = 45 * 60

#: Plafond de l'attente dans l'execution (le workflow doit pouvoir la
#: contenir dans son `timeout-minutes`).
MAX_WAIT_SECONDS = 55 * 60

#: Modes d'execution.
MODE_AUTO = "auto"
MODE_CHAIN = "chain"
MODES = (MODE_AUTO, MODE_CHAIN)

#: Resultats possibles de l'etape de publication de l'execution courante.
PUBLISHED_SUCCESS = "success"
PUBLISHED_SKIPPED = "skipped"
PUBLISHED_FAILURE = "failure"


class Plan(NamedTuple):
    """Decision de relance : declencher ou non, et apres quelle attente."""

    dispatch: bool
    wait_seconds: int
    reason: str


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
    """Age de la derniere publication, lu dans l'artefact publie a la reference.

    Le runner fait un checkout de profondeur 1 : l'historique des commits de
    publication n'y est pas. L'artefact `site/agent_analysis.json` porte
    revanche l'horodatage de la derniere publication : cette source est donc
    la plus fiable en exploitation.

    La reference `ref` designe l'etat *courant* de la branche publiee :

    - au debut de l'execution, `ref` vaut la tete de la branche et l'artefact
      est celui de la publication **precedente** (c'est l'age utilise par la
      porte de publication) ;
    - a la fin de l'execution, l'etape de publication a committe le nouvel
      artefact sur la branche locale : l'artefact est alors celui de la
      publication **que l'on vient de faire** (c'est l'age utilise pour
      caler le prochain creneau).
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


def should_publish(age_seconds: Optional[float],
                   min_interval_seconds: int = MIN_INTERVAL_SECONDS) -> bool:
    """Porte de publication : cette execution a-t-elle le droit de publier ?

    Une publication n'a lieu que si la derniere a plus de `min_interval_seconds`.
    Un age INCONNU n'interdit pas la publication (le site n'est jamais laisse
    sans donnee fraiche pour un simple doute) ; c'est la *relance* qui est
    bloquee en cas d'age inconnu, pas la publication.
    """
    if age_seconds is None:
        return True
    return age_seconds >= min_interval_seconds


def seconds_until_next_slot(age_seconds: Optional[float],
                            pace_seconds: int = PACE_SECONDS) -> int:
    """Secondes a attendre avant le prochain creneau de publication.

    L'age mesure est celui de la derniere publication : on attend que le
    creneau soit passe. Un age INCONNU attend un creneau complet : sans
    connaatre la date de la derniere publication, relancer immediatement
    ferait boucler la chaine (c'est exactement le defaut corrige en 2026-10-21).
    """
    if age_seconds is None:
        return pace_seconds
    remaining = pace_seconds - age_seconds
    return int(remaining) if remaining > 0 else 0


def chain_is_dead(age_seconds: Optional[float],
                  stale_seconds: int = CHAIN_STALE_SECONDS) -> bool:
    """Vrai si la chaine est arretee (et peut donc etre relancee).

    Un age inconnu ne prouve pas l'arret de la chaine : on ne relance pas
    (protection anti-boucle).
    """
    if age_seconds is None:
        return False
    return age_seconds >= stale_seconds


def plan_dispatch(mode: str,
                  age_seconds: Optional[float],
                  published: str = PUBLISHED_SUCCESS,
                  liveness_age_seconds: Optional[float] = None,
                  pace_seconds: int = PACE_SECONDS,
                  stale_seconds: int = CHAIN_STALE_SECONDS,
                  backoff_seconds: int = FAILURE_BACKOFF_SECONDS) -> Plan:
    """Decide si l'execution courante relance la suivante, et apres quelle attente.

    - `chain` : l'execution est un maillon de la chaine. Elle attend le
      prochain creneau puis relance. Si sa publication a echoue, elle attend le
      delai de repli (45 min) avant de retenter.
    - `auto` : l'execution est ponctuelle (cron, push, manuel). Elle ne relance
      que si la chaine est arretee, afin de ne jamais creer une chaine
      parallelle (les chaines s'accumuleraient).

    `age_seconds` est l'age de la **derniere** publication (celle que
    l'execution vient de faire, s'il y a lieu). `liveness_age_seconds` est
    l'age de la publication **precedente**, mesuree au commit de checkout :
    c'est l'etat de la chaine au moment ou l'execution a demarre. Sans cette
    distinction, une execution ponctuelle qui vient de publier verifierait sa
    propre publication, croirait la chaine toujours vivante, et ne pourrait
    donc jamais la relancer.
    """
    if mode == MODE_CHAIN:
        if published == PUBLISHED_FAILURE:
            return Plan(True, backoff_seconds,
                        f"publication en echec : nouvelle tentative apres {backoff_seconds / 60:.0f} min")
        wait = seconds_until_next_slot(age_seconds, pace_seconds)
        return Plan(True, wait,
                    f"maillon de chaine : publication suivante au plus tard dans {wait / 60:.1f} min")
    if liveness_age_seconds is None:
        liveness_age_seconds = age_seconds
    if liveness_age_seconds is None:
        return Plan(False, 0, "age inconnu : aucune relance (protection anti-boucle)")
    if not chain_is_dead(liveness_age_seconds, stale_seconds):
        return Plan(False, 0, "chaine vivante : aucune relance")
    return Plan(True, 0, "chaine arretee : relance du chainage")

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


def dispatch_workflow(repository: str, workflow: str, ref: str, token: str,
                      inputs: Optional[dict[str, str]] = None) -> bool:
    """Declenche une execution du workflow. Retourne True si la demande a ete acceptee."""
    url = f"https://api.github.com/repos/{repository}/actions/workflows/{workflow}/dispatches"
    payload: dict[str, Any] = {"ref": ref}
    if inputs:
        payload["inputs"] = inputs
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
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
    parser.add_argument("--mode", choices=MODES, default=MODE_AUTO,
                        help="auto : execution ponctuelle ; chain : maillon de la chaine")
    parser.add_argument("--published", choices=(PUBLISHED_SUCCESS, PUBLISHED_SKIPPED, PUBLISHED_FAILURE),
                        default=PUBLISHED_SUCCESS,
                        help="resultat de l'etape de publication de l'execution courante")
    parser.add_argument("--min-interval-min", type=float, default=MIN_INTERVAL_SECONDS / 60,
                        help="intervalle minimal entre deux publications, en minutes")
    parser.add_argument("--pace-min", type=float, default=PACE_SECONDS / 60,
                        help="duree du creneau entre deux publications de la chaine, en minutes")
    parser.add_argument("--stale-min", type=float, default=CHAIN_STALE_SECONDS / 60,
                        help="age sans publication au-dela duquel la chaine est consideree arretee")
    parser.add_argument("--backoff-min", type=float, default=FAILURE_BACKOFF_SECONDS / 60,
                        help="delai de repli apres un echec de publication, en minutes")
    parser.add_argument("--checkout-ref", default="",
                        help="commit de checkout : mesure l'etat de la chaine au demarrage "
                             "de l'execution (relance d'une chaine arretee)")
    parser.add_argument("--decide", action="store_true",
                        help="decide de la publication (porte) sans relancer quoi que ce soit")
    parser.add_argument("--github-output", default="",
                        help="fichier $GITHUB_OUTPUT a completer (mode --decide)")
    parser.add_argument("--no-wait", action="store_true",
                        help="n'attend pas le prochain creneau (tests, diagnostic)")
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
    age = None
    source = "aucune source"
    try:
        entries, head_is_current = read_git_entries(".", ref=args.ref)
        # Source prioritaire : l'artefact publie sur la branche (fonctionne
        # meme avec un checkout de profondeur 1). Secours : l'historique git.
        age = previous_publication_age_from_artifact(".", ref=args.ref)
        source = "artefact publie sur la branche"
        if age is None:
            age = previous_publication_age(entries, datetime.now(timezone.utc), head_is_current)
            source = "historique des commits de publication"
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Auto-relance ignoree (lecture git impossible : {exc})")
        return 0

    age_text = "age inconnu (aucune relance)" if age is None else f"{age/60:.1f} min"

    if args.decide:
        gate = int(args.min_interval_min * 60)
        allowed = should_publish(age, gate)
        print(f"Porte de publication : derniere publication {age_text} (source : {source}) ; "
              f"intervalle minimal {gate/60:.0f} min -> "
              f"{'PUBLICATION AUTORISEE' if allowed else 'PUBLICATION DIFFEREE'}")
        if args.github_output:
            try:
                with open(args.github_output, "a", encoding="utf-8") as stream:
                    stream.write(f"publish={'true' if allowed else 'false'}\n")
            except OSError as exc:
                print(f"  (ecriture $GITHUB_OUTPUT impossible : {exc})")
        return 0

    # Etat de la chaine AU DEMARRAGE de l'execution : publication precedente,
    # mesuree au commit de checkout. Sans cela, une execution ponctuelle qui
    # vient de publier verifierait sa propre publication et croirait la
    # chaine toujours vivante -- elle ne pourrait jamais la relancer.
    liveness_age = None
    if args.checkout_ref:
        try:
            liveness_age = previous_publication_age_from_artifact(".", ref=args.checkout_ref)
        except Exception:  # pragma: no cover - defensive
            liveness_age = None
    plan = plan_dispatch(args.mode, age, args.published,
                          liveness_age_seconds=liveness_age,
                          pace_seconds=int(args.pace_min * 60),
                          stale_seconds=int(args.stale_min * 60),
                          backoff_seconds=int(args.backoff_min * 60))
    live_text = "" if liveness_age is None else f" ; chaine vue au demarrage {liveness_age/60:.1f} min"
    print(f"Auto-relance : derniere publication {age_text} (source : {source}) ; mode {args.mode} "
          f"-> {'RELANCE' if plan.dispatch else 'inutile'}{live_text} ; {plan.reason}")

    if not plan.dispatch:
        return 0

    wait = min(max(int(plan.wait_seconds), 0), MAX_WAIT_SECONDS)
    if wait and not args.no_wait and not args.dry_run:
        print(f"  attente du prochain creneau ({wait/60:.1f} min)")
        try:
            time.sleep(wait)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  attente interrompue ({type(exc).__name__} : {exc})")
    if args.dry_run:
        print("  (mode simulation : aucune requete effectuee)")
        return 0

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token or not args.repository:
        print("  Auto-relance impossible : jeton ou depot absent")
        return 0
    try:
        # Le successeur est toujours un maillon de chaine : c'est ce qui
        # garantit qu'une seule chaine tourne a la fois.
        accepted = dispatch_workflow(args.repository, args.workflow, args.ref, token,
                                      inputs={"mode": MODE_CHAIN})
    except Exception as exc:  # cette etape ne doit jamais faire echouer la publication
        print(f"  Auto-relance ignoree ({type(exc).__name__} : {exc})")
        return 0
    print(f"  Auto-relance {'declenchee' if accepted else 'refusee'} "
          f"({args.repository}/{args.workflow} sur {args.ref}, mode {MODE_CHAIN})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

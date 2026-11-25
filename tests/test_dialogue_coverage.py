"""Offline regression for current-user intent and bounded response coverage."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import time

from scripts.agents.automation import command_center_service as cc

QUESTION = ("Je dispose d'un ordinateur Windows avec 16 Go de RAM, aucun GPU dédié et aucun budget supplémentaire. "
            "Je souhaite créer une entreprise dont une grande partie du travail serait réalisée par des agents IA. "
            "Propose-moi trois activités commerciales réalistes, compare leur rentabilité potentielle, leurs difficultés et leurs risques. "
            "Choisis la plus pertinente et explique précisément comment ton équipe pourrait la développer avec mes ressources actuelles. "
            "Distingue ce que vous savez réellement faire de ce qui nécessite encore des capacités supplémentaires.")
BAD = "Nous devons réinitialiser le Data Pipeline. Veuillez spécifier le domaine."
GOOD = """Option 1 : Audit de données publiques avec contrôle humain.
Option 2 : Documentation de logiciels pour petites entreprises.
Option 3 : Veille commerciale à partir de sources autorisées.
Comparaison : L'audit demande plus de validation; la documentation est plus accessible.
Rentabilite : Les revenus restent hypothétiques, à tester auprès de clients.
Faisabilite et difficultes : CPU seul, tâches séquentielles, contrôle humain.
Risques : Erreurs de données, droits d'accès, confidentialité.
Choix recommande : Documentation technique, faible coût et test rapide.
Plan concret : Créer un exemple, prospecter manuellement, valider un pilote.
Capacites et limites : Rédaction et code possibles; vente et accès externes non prouvés."""

class DialogueCoverageTests(unittest.TestCase):
    def test_exact_owner_request_contract(self):
        contract = cc.dialogue_contract(QUESTION)
        self.assertEqual(len(contract), 10)
        self.assertEqual(len(cc.dialogue_missing(contract, BAD)), 10)
        self.assertEqual(cc.dialogue_missing(contract, GOOD), [])

    def test_headings_alone_do_not_pass(self):
        contract = cc.dialogue_contract(QUESTION)
        self.assertTrue(cc.dialogue_missing(contract, "\n".join(label for _, label in contract)))
        self.assertEqual(cc.dialogue_contract("Quel est le nom de notre projet ?"), [])

    def test_later_queued_turn_excluded(self):
        msgs = [{"role":"user","id":"a","content":"ancien"}, {"role":"assistant","content":"réponse"},
                {"role":"user","id":"b","content":QUESTION}, {"role":"user","id":"c","content":"nouvelle demande"}]
        self.assertEqual(cc._prior_messages_for_job(msgs, {"user_message_id":"b","prompt_text":QUESTION}), msgs[:2])

    def _run(self, second_reply):
        calls = []
        def fake(**kwargs):
            calls.append(kwargs)
            n = len(calls)
            return {"response": BAD if n <= 3 else second_reply, "provider_used":"stub",
                    "model_used":"stub","cloud_calls":0,"duration_seconds":0.01}
        with tempfile.TemporaryDirectory() as tmp:
            svc = cc.CommandCenterService(Path(tmp), model_caller=fake)
            conv = svc.create_conversation(title="Regression", role="coordination", team_mode=True)
            j = svc.submit_chat_message(conv_id=conv["id"], message=QUESTION)
            for _ in range(200):
                result = svc.get_job(j["job_id"])
                if result["status"] in ("DONE","ERROR","CANCELLED"):
                    break
                time.sleep(0.025)
            self.assertEqual(result["status"], "DONE", str(result.get("error")))
            self.assertEqual(len(calls), 4)
            self.assertEqual(len(result["assistant_message"]["delegated_specialists"]), 2)
            self.assertTrue(all(c["confidential"] and not c["hybrid"] for c in calls))
            self.assertTrue(calls[2]["prompt"].endswith(QUESTION))
            self.assertIn("Rubriques manquantes", calls[3]["system"])
            return result["assistant_message"]

    def test_repair_after_bad_synthesis(self):
        message = self._run(GOOD)
        self.assertEqual(message["coverage_check"]["missing_sections"], [])
        self.assertEqual(message["content"], GOOD)

    def test_persistent_failure_labeled_partial(self):
        message = self._run(BAD)
        self.assertTrue(message["coverage_check"]["missing_sections"])
        self.assertTrue(message["content"].startswith("Réponse partielle"))

if __name__ == "__main__":
    unittest.main()

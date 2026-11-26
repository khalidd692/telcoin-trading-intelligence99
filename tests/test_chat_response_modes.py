"""Offline regression: adaptive chat modes preserve privacy and avoid unnecessary calls."""
from pathlib import Path
import tempfile
import time
import unittest

from scripts.agents.automation import command_center_service as cc

BUSINESS = "Propose trois activités commerciales réalistes, compare leur rentabilité, leurs difficultés et leurs risques. Choisis la meilleure et donne un plan concret."
TECHNICAL = "Compare trois solutions Python pour une API locale, explique les risques et choisis la meilleure."
COMPLETE = """Option 1 : Documentation technique et guides pour indépendants.
Option 2 : Veille commerciale sur des sources publiques autorisées.
Option 3 : Audit de données avec validation humaine obligatoire.
Comparaison : La documentation demande le moins de ressources initiales.
Rentabilite : Revenus hypothétiques, à mesurer auprès de prospects.
Faisabilite et difficultes : CPU seul, tâches séquentielles, validation manuelle.
Risques : Erreurs de contenu, confidentialité et droits d'accès.
Choix recommande : Documentation technique et validation par un client.
Plan concret : Préparer un exemple, tester auprès de trois prospects."""

class ResponseModeTests(unittest.TestCase):
    def test_auto_short_and_business_no_delegation(self):
        for question in ("Bonjour, comment ça va ?", BUSINESS):
            self.assertEqual(cc.plan_dialogue_delegation(question, mode="auto", team_mode=True), 0)

    def test_auto_complex_and_explicit_delegation(self):
        self.assertEqual(cc.plan_dialogue_delegation(TECHNICAL, mode="auto", team_mode=True), 1)
        self.assertEqual(cc.plan_dialogue_delegation("Mobilise les spécialistes pour analyser ce projet.", mode="auto", team_mode=True), 2)
        self.assertEqual(cc.plan_dialogue_delegation("Audit de sécurité", mode="auto", team_mode=True), 2)

    def test_mode_validation_and_override(self):
        self.assertEqual(cc.plan_dialogue_delegation("Audit de sécurité", mode="fast", team_mode=True), 0)
        self.assertEqual(cc.plan_dialogue_delegation(BUSINESS, mode="deep", team_mode=True), 2)
        self.assertEqual(cc.plan_dialogue_delegation(BUSINESS, mode="deep", team_mode=False), 0)
        with self.assertRaises(ValueError):
            cc.plan_dialogue_delegation("hello", mode="unknown", team_mode=True)

    def run_job(self, mode, text, reply):
        calls = []
        def fake(**kwargs):
            calls.append(kwargs)
            return {"response": reply, "provider_used":"stub","model_used":"stub","cloud_calls":0,"duration_seconds":0.01}
        with tempfile.TemporaryDirectory() as tmp:
            svc = cc.CommandCenterService(Path(tmp), model_caller=fake)
            conv = svc.create_conversation(role="coordination", team_mode=True, confidential=True, hybrid=True)
            j = svc.submit_chat_message(conv_id=conv["id"], message=text, response_mode=mode)
            for _ in range(200):
                result = svc.get_job(j["job_id"])
                if result["status"] in ("DONE","ERROR","CANCELLED"):
                    break
                time.sleep(0.025)
            self.assertEqual(result["status"], "DONE", str(result.get("error")))
            self.assertTrue(all(c["confidential"] and not c["hybrid"] for c in calls))
            return result["assistant_message"], calls

    def test_auto_business_one_call_complete(self):
        msg, calls = self.run_job("auto", BUSINESS, COMPLETE)
        self.assertEqual(len(calls), 1)
        self.assertEqual(msg["response_mode"], "auto")
        self.assertEqual(msg["delegated_specialists"], [])
        self.assertEqual(msg["coverage_check"]["missing_sections"], [])

    def test_fast_incomplete_flagged_without_second_call(self):
        msg, calls = self.run_job("fast", BUSINESS, "Réponse vague")
        self.assertEqual(len(calls), 1)
        self.assertTrue(msg["content"].startswith("Réponse partielle"))

    def test_deep_preserves_three_calls_for_simple_request(self):
        msg, calls = self.run_job("deep", "Explique la structure du projet.", "Une structure simple.")
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(msg["delegated_specialists"]), 2)

if __name__ == "__main__":
    unittest.main()

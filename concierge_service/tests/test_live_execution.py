"""Host execution integration against fake HTTP and a real isolated SQLite ledger."""
import copy
import gc
import tempfile
import unittest
from pathlib import Path

from concierge_service.live_execution import execute_decision
from concierge_service.reviewed_transport import UncertainDelivery
from concierge_service.tests.test_engine_safety import A, setup, command, consent_all

PARTY = "27820000002@s.whatsapp.net"


class Client:
    account_id, base, key = "provider", "https://api.unipile.com/api/v1", "synthetic-secret"

    def __init__(self):
        self.writes = []
        self.messages = []
        self.members = [PARTY]
        self.crash = False
        self.timeout = False

    def verify_account(self):
        return {"id": self.account_id, "type": "WHATSAPP"}

    def list_chats(self):
        return [{"id": "chat"}] if self.messages else []

    def fetch_conversation(self, cid):
        return {"account_id": self.account_id, "chat_id": cid, "all_history": True,
                "recipients": list(self.members), "messages": copy.deepcopy(self.messages)}

    def http(self, method, url, headers, body):
        self.writes.append((method, url, body))
        if self.crash:
            raise KeyboardInterrupt("simulated process death")
        if self.timeout:
            raise TimeoutError()
        self.messages.append({"message_id": "sent", "chat_id": "chat", "account_id": self.account_id,
            "text": body["text"], "is_sender": True, "timestamp": "2020-01-02T00:00:00Z", "sender_id": None})
        self.members = body.get("attendees_ids", self.members)
        return 200, {}, {"chat_id": "chat", "message_id": "sent"}


class LiveExecutionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(gc.collect)
        self.engine = setup(Path(self.temp.name), "live")
        self.client = Client()
        self.engine.unipile[A] = self.client
        command(self.engine, "start")
        command(self.engine, "consent", party="recipient", scope="contact", source_ref="operator:permission")
        self.decision = self.stage("approach")
        self.gate = lambda canonical, invoke: invoke()

    def stage(self, purpose):
        with self.engine.store.transaction() as db:
            doc = self.engine.store.load(db, A, "live")
            decision = self.engine.stage(doc, doc["prospects"][0], purpose, "Hello")
            self.engine.store.save(db, doc)
        return decision["id"]

    def doc(self):
        with self.engine.store.transaction() as db:
            return self.engine.store.load(db, A, "live")

    def test_external_gate_refusal_is_inert_and_payload_shows_exact_sender(self):
        cards = []
        def gate(action, invoke):
            cards.append(action)
            return {"status": "AWAITING_CONFIRMATION"}
        result = execute_decision(self.engine, A, self.decision, gate)
        self.assertEqual(result["status"], "AWAITING_CONFIRMATION")
        self.assertEqual(cards[0]["sender"], "provider")
        self.assertEqual(cards[0]["recipients"], [PARTY])
        self.assertFalse(self.client.writes)
        self.assertNotIn("live_dispatch_claims", self.doc())

    def test_verified_dispatch_persists_provider_receipt_and_cannot_repeat(self):
        result = execute_decision(self.engine, A, self.decision, self.gate)
        self.assertTrue(result["message_verified"])
        doc = self.doc()
        self.assertEqual(doc["live_dispatch_claims"][self.decision]["status"], "verified")
        self.assertEqual(doc["messages"][-1]["id"], "sent")
        self.assertEqual(doc["messages"][-1]["provider_account_id"], "provider")
        self.assertFalse(doc["messages"][-1]["simulated"])
        self.assertEqual(doc["decisions"][-1]["status"], "executed")
        with self.assertRaises(ValueError):
            execute_decision(self.engine, A, self.decision, self.gate)
        self.assertEqual(len(self.client.writes), 1)

    def test_process_death_after_post_keeps_durable_start(self):
        self.client.crash = True
        with self.assertRaises(KeyboardInterrupt):
            execute_decision(self.engine, A, self.decision, self.gate)
        doc = self.doc()
        self.assertEqual(doc["live_dispatch_claims"][self.decision]["status"], "started")
        self.assertEqual(self.engine.state(doc, "p")["status"], "reconcile")
        with self.assertRaises(ValueError):
            execute_decision(self.engine, A, self.decision, self.gate)
        self.assertEqual(len(self.client.writes), 1)

    def test_timeout_records_unknown_without_retry(self):
        self.client.timeout = True
        with self.assertRaises(UncertainDelivery):
            execute_decision(self.engine, A, self.decision, self.gate)
        self.assertEqual(self.doc()["live_dispatch_claims"][self.decision]["status"], "unknown")
        self.assertEqual(len(self.client.writes), 1)

    def test_provider_historical_decline_blocks_before_claim(self):
        self.client.messages = [{"message_id": "decline", "text": "No thanks", "is_sender": False,
            "timestamp": "2020-01-01T00:00:00Z", "sender_id": PARTY}]
        with self.assertRaises(ValueError):
            execute_decision(self.engine, A, self.decision, self.gate)
        self.assertFalse(self.client.writes)
        self.assertNotIn("live_dispatch_claims", self.doc())

    def test_inbound_while_gate_pending_invalidates_action(self):
        def gate(action, invoke):
            self.engine.ingest(A, "p", "STOP", "stop", "chat", PARTY, "2020-01-01T00:00:00Z", "unipile:test")
            return invoke()
        with self.assertRaises(ValueError):
            execute_decision(self.engine, A, self.decision, gate)
        self.assertFalse(self.client.writes)

    def test_group_requires_explicit_real_principal_identity(self):
        consent_all(self.engine)
        decision = self.stage("introduction")
        with self.assertRaises(ValueError):
            execute_decision(self.engine, A, decision, self.gate)
        result = execute_decision(self.engine, A, decision, self.gate,
                                  principal_provider_id="27820000001@s.whatsapp.net")
        self.assertTrue(result["membership_verified"])
        self.assertTrue(self.doc()["messages"][-1]["group"])
        self.assertEqual(self.doc()["prospects"][0]["group_chat_id"], "chat")

    def test_payload_tampering_cannot_reuse_decision_id(self):
        with self.engine.store.transaction() as db:
            doc = self.engine.store.load(db, A, "live")
            doc["decisions"][-1]["text"] = "Changed after review"
            self.engine.store.save(db, doc)
        with self.assertRaises(ValueError):
            execute_decision(self.engine, A, self.decision, self.gate)
        self.assertFalse(self.client.writes)

    def test_changed_phone_while_gate_pending_refuses(self):
        def gate(action, invoke):
            with self.engine.store.transaction() as db:
                doc = self.engine.store.load(db, A, "live")
                doc["prospects"][0]["phone"] = "+27820000003"
                self.engine.store.save(db, doc)
            return invoke()
        with self.assertRaises(ValueError):
            execute_decision(self.engine, A, self.decision, gate)
        self.assertFalse(self.client.writes)

    def test_reply_requires_current_verified_unanswered_message(self):
        self.engine.ingest(A, "p", "What is it?", "incoming", "chat", PARTY,
                           "2020-01-01T00:00:00Z", "unipile:test")
        self.client.messages = [{"message_id": "incoming", "text": "What is it?", "is_sender": False,
            "timestamp": "2020-01-01T00:00:00Z", "sender_id": PARTY}]
        decision = self.stage("reply")
        result = execute_decision(self.engine, A, decision, self.gate)
        self.assertTrue(result["message_verified"])
        self.assertTrue(self.client.writes[0][1].endswith("/chats/chat/messages"))


if __name__ == "__main__":
    unittest.main()

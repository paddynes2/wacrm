"""Offline polling evidence checks with a real transactional store."""
import copy
import gc
import tempfile
import unittest
from pathlib import Path

from concierge_service.engine import Engine
from concierge_service.store import Store
from concierge_service.ingestion import sync_account
from concierge_service.providers import ProviderError

ACCOUNT = "11111111-1111-4111-8111-111111111111"
PHONE = "+27820000001"
PARTY = "27820000001@s.whatsapp.net"


class FakeProvider:
    account_id = "provider-account"

    def __init__(self):
        self.snapshots = {"chat": {"account_id": self.account_id, "chat_id": "chat", "all_history": True,
            "recipients": [PARTY], "messages": [{"message_id": "m1", "chat_id": "chat", "account_id": self.account_id,
                "timestamp": "2020-01-01T00:00:00Z", "is_sender": False, "sender_id": PARTY, "text": "Hello"}]}}
        self.fail = False

    def verify_account(self):
        return {"id": self.account_id, "type": "WHATSAPP"}

    def list_chats(self):
        return [{"id": cid, "account_id": self.account_id} for cid in self.snapshots]

    def fetch_conversation(self, cid):
        if self.fail:
            raise RuntimeError("private provider response secret")
        return copy.deepcopy(self.snapshots[cid])


class RecordingEngine(Engine):
    """Reconciliation uses the real store; ingestion calls record their exact args."""
    def __init__(self, store, provider):
        super().__init__(store, mode="live", unipile={ACCOUNT: provider})
        self.incoming, self.manual = [], []

    def state(self, doc, pid):
        return {"status": "active", "identity": {"recipient_id": self.prospect(doc, pid)["phone"], "principal_id": "principal:unbound"}}

    def ingest(self, *args):
        if args not in self.incoming:
            self.incoming.append(args)

    def manual_outbound(self, *args):
        if args not in self.manual:
            self.manual.append(args)


class IngestionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(gc.collect)
        self.provider = FakeProvider()
        self.engine = RecordingEngine(Store(Path(self.temp.name) / "execution.db"), self.provider)
        with self.engine.store.transaction() as db:
            doc = self.engine.store.load(db, ACCOUNT, "live")
            doc["prospects"].append({"id": "p1", "phone": PHONE, "phone_status": "operator_verified"})
            self.engine.store.save(db, doc)

    def document(self):
        with self.engine.store.transaction() as db:
            return self.engine.store.load(db, ACCOUNT, "live")

    def test_new_chat_matching_phone_and_repeat_sync(self):
        result = sync_account(self.engine, ACCOUNT)
        self.assertEqual(result["inbound"], 1)
        self.assertFalse(result["live_delivery_verified"])
        self.assertEqual(self.engine.incoming[0][:6], (ACCOUNT, "p1", "Hello", "m1", "chat", PARTY))
        self.assertTrue(self.engine.incoming[0][-1].startswith("unipile:sha256:"))
        sync_account(self.engine, ACCOUNT)
        self.assertEqual(len(self.engine.incoming), 1)
        saved = self.document()["connections"]
        self.assertEqual(saved["chat_checkpoints"]["chat"]["last_message_id"], "m1")
        self.assertTrue(saved["last_sync"])

    def test_unknown_chat_not_claimed(self):
        self.provider.snapshots["chat"]["recipients"] = ["27820000002@s.whatsapp.net"]
        self.provider.snapshots["chat"]["messages"][0]["sender_id"] = "27820000002@s.whatsapp.net"
        result = sync_account(self.engine, ACCOUNT)
        self.assertEqual(result["unknown_chats"], ["chat"])
        self.assertFalse(self.engine.incoming)
        self.assertEqual(len(self.document()["prospects"]), 1)

    def test_ambiguous_prospect_phone_not_claimed(self):
        with self.engine.store.transaction() as db:
            doc = self.engine.store.load(db, ACCOUNT, "live")
            doc["prospects"].append({"id": "p2", "phone": PHONE, "phone_status": "operator_verified"})
            self.engine.store.save(db, doc)
        self.assertEqual(sync_account(self.engine, ACCOUNT)["unknown_chats"], ["chat"])
        self.assertFalse(self.engine.incoming)

    def test_group_with_extra_person_not_claimed(self):
        self.provider.snapshots["chat"]["recipients"].append("27820000002@s.whatsapp.net")
        self.assertEqual(sync_account(self.engine, ACCOUNT)["unknown_chats"], ["chat"])

    def test_manual_outbound_and_media_preserved(self):
        message = self.provider.snapshots["chat"]["messages"][0]
        message.update(is_sender=True, sender_id=None, text=None)
        result = sync_account(self.engine, ACCOUNT)
        self.assertEqual(result["manual_outbound"], 1)
        self.assertIsNone(self.engine.manual[0][2])
        self.assertFalse(self.engine.incoming)

    def test_exact_receipt_echo_does_not_claim_manual_origin(self):
        self.provider.snapshots["chat"]["messages"][0].update(is_sender=True, sender_id=None)
        with self.engine.store.transaction() as db:
            doc = self.engine.store.load(db, ACCOUNT, "live")
            doc["messages"].append({"id": "m1", "prospect_id": "p1", "direction": "outbound", "simulated": False,
                "chat_id": "chat", "provider_account_id": "provider-account", "text": "Hello", "purpose": "reply"})
            self.engine.store.save(db, doc)
        self.assertEqual(sync_account(self.engine, ACCOUNT)["assistant_echoes"], 1)
        self.assertFalse(self.engine.manual)

    def test_receipt_in_other_chat_is_not_an_echo(self):
        self.provider.snapshots["chat"]["messages"][0].update(is_sender=True, sender_id=None)
        with self.engine.store.transaction() as db:
            doc = self.engine.store.load(db, ACCOUNT, "live")
            doc["messages"].append({"id": "m1", "prospect_id": "p1", "direction": "outbound", "simulated": False,
                "chat_id": "other", "provider_account_id": "provider-account", "text": "Hello", "purpose": "reply"})
            self.engine.store.save(db, doc)
        self.assertEqual(sync_account(self.engine, ACCOUNT)["manual_outbound"], 1)

    def test_invalid_evidence_has_no_message_side_effects(self):
        baseline = copy.deepcopy(self.provider.snapshots["chat"])
        for change in ("partial", "wrong_account", "wrong_sender", "duplicate", "missing_time"):
            self.provider.snapshots["chat"] = copy.deepcopy(baseline)
            snapshot = self.provider.snapshots["chat"]
            if change == "partial":
                snapshot["all_history"] = False
            elif change == "wrong_account":
                snapshot["account_id"] = "other"
            elif change == "wrong_sender":
                snapshot["messages"][0]["sender_id"] = "other"
            elif change == "duplicate":
                snapshot["messages"].append(copy.deepcopy(snapshot["messages"][0]))
            else:
                del snapshot["messages"][0]["timestamp"]
            with self.assertRaises(ProviderError):
                sync_account(self.engine, ACCOUNT)
            self.assertFalse(self.engine.incoming)
            self.assertNotIn("last_sync", self.document()["connections"])

    def test_provider_failure_preserves_checkpoint_and_sanitizes(self):
        sync_account(self.engine, ACCOUNT)
        checkpoint = self.document()["connections"]["last_sync"]
        self.provider.fail = True
        with self.assertRaises(ProviderError) as error:
            sync_account(self.engine, ACCOUNT)
        self.assertNotIn("secret", str(error.exception))
        self.assertEqual(self.document()["connections"]["last_sync"], checkpoint)
        self.assertTrue(self.document()["connections"]["last_sync_error"])

    def test_second_chat_failure_prevents_first_chat_ingestion(self):
        self.provider.snapshots["second"] = {"account_id": "provider-account", "chat_id": "second", "all_history": False}
        with self.assertRaises(ProviderError):
            sync_account(self.engine, ACCOUNT)
        self.assertFalse(self.engine.incoming)

    def test_multiple_new_chats_for_same_person_are_ambiguous(self):
        second = copy.deepcopy(self.provider.snapshots["chat"])
        second["chat_id"] = "second"
        second["messages"][0].update(chat_id="second", message_id="m2")
        self.provider.snapshots["second"] = second
        result = sync_account(self.engine, ACCOUNT)
        self.assertEqual(result["unknown_chats"], ["chat", "second"])
        self.assertFalse(self.engine.incoming)

    def test_real_engine_ingestion_stops_and_deduplicates(self):
        runtime = Engine(self.engine.store, mode="live", unipile={ACCOUNT: self.provider})
        with runtime.store.transaction() as db:
            doc = runtime.store.load(db, ACCOUNT, "live")
            p = doc["prospects"][0]
            p.update(name="Alex", fit="Verified test fit", source="test:evidence", qualification="qualified", brief_stale=False)
            runtime.observe(doc, "p1", "identified", {"crm_ref": "test:p1", "principal_id": "principal:" + ACCOUNT,
                "recipient_id": PHONE, "principal_name": "Principal", "name": "Alex", "offer": "Advice",
                "fit": "Verified test fit", "profile_url": "https://example.invalid/person"})
            runtime.store.save(db, doc)
        self.provider.snapshots["chat"]["messages"][0]["text"] = "STOP"
        sync_account(runtime, ACCOUNT)
        sync_account(runtime, ACCOUNT)
        doc = self.document()
        self.assertEqual(len(doc["messages"]), 1)
        self.assertEqual(runtime.state(doc, "p1")["status"], "opted_out")
        self.assertEqual(doc["prospects"][0]["chat_id"], "chat")

    def test_other_tenant_has_no_provider(self):
        with self.assertRaises(ProviderError):
            sync_account(self.engine, "22222222-2222-4222-8222-222222222222")
        self.assertFalse(self.engine.incoming)


if __name__ == "__main__":
    unittest.main()

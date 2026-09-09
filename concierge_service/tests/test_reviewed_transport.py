"""All writes terminate in FakeClient. No production gate/config is armed."""
import copy
import unittest
from concierge_service.reviewed_transport import canonical_action, execute_reviewed, UncertainDelivery
from concierge_service.providers import ProviderError

PARTY = "27820000001@s.whatsapp.net"


class Client:
    account_id, base, key = "provider", "https://api.unipile.com/api/v1", "synthetic"

    def __init__(self):
        self.writes = []
        self.bad_readback = False
        self.timeout = False
        self.recipients = [PARTY]

    def verify_account(self):
        return {"id": self.account_id, "type": "WHATSAPP"}

    def list_chats(self):
        return [{"id": "chat"}]

    def fetch_conversation(self, cid):
        return {"recipients": self.recipients, "messages": ([{"message_id": "sent", "is_sender": True,
            "text": "wrong" if self.bad_readback else "Hello", "timestamp": "2020-01-01T00:00:00Z"}] if self.writes else [])}

    def http(self, method, url, headers, body):
        self.writes.append((method, url, body))
        if self.timeout:
            raise TimeoutError()
        return 200, {}, {"chat_id": "chat", "message_id": "sent"}


class ReviewedTransportTest(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.action = {"action_id": "a", "workspace_id": "11111111-1111-4111-8111-111111111111",
            "prospect_id": "p", "account_id": "provider", "recipients": [PARTY], "text": "Hello",
            "revision": "a" * 64, "purpose": "reply", "chat_id": "chat"}
        self.records, self.claimed = [], set()
        def claim(digest, action):
            if digest in self.claimed:
                return False
            self.claimed.add(digest)
            return True
        def record(digest, action, status, evidence):
            self.records.append((status, evidence))
            return True
        self.callbacks = {"gate": lambda action, send: send(), "validate_current": lambda action: True,
                          "inspect_thread": lambda snapshot, action: True, "claim": claim, "record": record}

    def test_missing_gate_or_refusal_never_calls_provider(self):
        with self.assertRaises(ProviderError):
            execute_reviewed(self.client, self.action)
        self.callbacks["gate"] = lambda action, send: {"status": "AWAITING_CONFIRMATION"}
        result = execute_reviewed(self.client, self.action, **self.callbacks)
        self.assertEqual(result["status"], "AWAITING_CONFIRMATION")
        self.assertFalse(self.client.writes)

    def test_account_and_payload_in_canonical_allowlist(self):
        value = canonical_action(self.action)
        self.assertEqual(value["sender"], "provider")
        self.assertEqual(value["payload"]["workspace_id"], self.action["workspace_id"])
        self.assertEqual(set(value), {"kind", "channel", "sender", "endpoint", "recipients", "payload"})

    def test_verified_readback_and_durable_replay_refusal(self):
        result = execute_reviewed(self.client, self.action, **self.callbacks)
        self.assertTrue(result["message_verified"])
        self.assertFalse(result["delivered_to_recipient"])
        self.assertEqual([row[0] for row in self.records], ["started", "verified"])
        self.assertEqual(self.client.writes[0][2], {"account_id": "provider", "text": "Hello"})
        with self.assertRaises(ProviderError):
            execute_reviewed(self.client, self.action, **self.callbacks)
        self.assertEqual(len(self.client.writes), 1)

    def test_unknown_keys_and_recipient_redirect_rejected(self):
        with self.assertRaises(ProviderError):
            execute_reviewed(self.client, {**self.action, "bypass": True}, **self.callbacks)
        bad = {**self.action, "recipients": ["27820000002@s.whatsapp.net"]}
        with self.assertRaises(ProviderError):
            execute_reviewed(self.client, bad, **self.callbacks)
        self.assertFalse(self.client.writes)

    def test_mutation_by_gate_does_not_change_approved_payload(self):
        def bad_gate(action, send):
            action["payload"]["text"] = "different"
            return send()
        with self.assertRaises(ProviderError):
            execute_reviewed(self.client, self.action, **{**self.callbacks, "gate": bad_gate})
        self.assertFalse(self.client.writes)

    def test_state_or_history_refusal_and_unwritable_ledger(self):
        for callback in ("validate_current", "inspect_thread", "claim", "record"):
            self.claimed.clear()
            with self.assertRaises(ProviderError):
                execute_reviewed(self.client, self.action, **{**self.callbacks, callback: lambda *args: False})
            self.assertFalse(self.client.writes)

    def test_provider_timeout_is_uncertain_and_not_retried(self):
        self.client.timeout = True
        with self.assertRaises(UncertainDelivery):
            execute_reviewed(self.client, self.action, **self.callbacks)
        self.assertEqual(len(self.client.writes), 1)
        self.assertEqual(self.records[-1][0], "unknown")

    def test_receipt_readback_mismatch_is_uncertain(self):
        self.client.bad_readback = True
        with self.assertRaises(UncertainDelivery):
            execute_reviewed(self.client, self.action, **self.callbacks)
        self.assertEqual(len(self.client.writes), 1)
        self.assertEqual(self.records[-1][0], "unknown")

    def test_gate_cannot_call_same_callable_twice(self):
        def twice(action, send):
            send()
            return send()
        with self.assertRaises(ProviderError):
            execute_reviewed(self.client, self.action, **{**self.callbacks, "gate": twice})
        self.assertEqual(len(self.client.writes), 1)

    def test_group_requires_exact_membership_and_verified_message(self):
        people = [PARTY, "27820000002@s.whatsapp.net"]
        self.client.recipients = people
        action = {**self.action, "purpose": "introduction", "recipients": people}
        del action["chat_id"]
        result = execute_reviewed(self.client, action, **self.callbacks)
        self.assertTrue(result["membership_verified"])
        self.assertEqual(self.client.writes[0][1], "https://api.unipile.com/api/v1/chats")
        self.assertEqual(self.client.writes[0][2]["attendees_ids"], people)


if __name__ == "__main__":
    unittest.main()

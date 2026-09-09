"""Offline request-contract and adversarial tests; no provider calls."""
import json
import unittest
from urllib.parse import urlsplit, parse_qs

from concierge_service.providers import discover, generate, UnipileClient, ProviderError


class ProvidersTest(unittest.TestCase):
    def treg(self, rows=None, **changes):
        data = {"output": {"people": rows if rows is not None else [{"firstName": "Alex", "lastName": "Example", "jobTitle": "Founder", "company": {"name": "Example", "domain": "example.invalid"}}]},
                "_treg": {"outcome": "hit", "served_by": "leadsforge.people.search", "charged_micro": 10000}}
        data.update(changes)
        return data

    def test_fixture_explicit_synthetic_no_phone(self):
        result = discover({"audience": "Founders"}, 3, {"provider": "fixture"})
        self.assertEqual(result["cost_usd"], 0)
        self.assertEqual(len(result["prospects"]), 3)
        self.assertTrue(all(p["phone"] is None and p["source"] == "fixture:synthetic" for p in result["prospects"]))
        self.assertEqual(result, discover({"audience": "Founders"}, 3, {"provider": "fixture"}))

    def test_treg_wire_and_unverified_result(self):
        calls = []
        def fake(*args):
            calls.append(args)
            return 200, {"X-Treg-Cost-Micro": "20000"}, self.treg()
        result = discover({"audience": "founders", "geography": "South Africa"}, 5,
                          {"provider": "treg", "token": "test-secret", "max_cost_usd": 0.25, "http": fake})
        self.assertEqual(calls[0][0:2], ("POST", "https://treg.to/call/treg.people.search"))
        self.assertEqual(calls[0][2]["X-Treg-Route-Max-Cost"], "0.2500")
        self.assertEqual(calls[0][3], {"q": "founders", "location": "South Africa", "limit": 5})
        self.assertEqual(result["cost_usd"], 0.02)
        self.assertEqual(result["prospects"][0]["phone_status"], "missing")
        self.assertEqual(result["prospects"][0]["domain"], "example.invalid")

    def test_invalid_config_never_calls(self):
        def forbidden(*args):
            self.fail("must not call")
        base = {"provider": "treg", "token": "secret", "max_cost_usd": 1, "http": forbidden}
        for change in ({"token": ""}, {"max_cost_usd": 0}, {"max_cost_usd": float("nan")},
                       {"base_url": "https://evil.invalid"}, {"filters": {"unknown": "x"}}):
            with self.subTest(change=change), self.assertRaises(ProviderError):
                discover({"audience": "x"}, 1, {**base, **change})
        for limit in (0, 101, True, 2.5):
            with self.assertRaises(ProviderError):
                discover({}, limit, {"provider": "fixture"})

    def test_malformed_and_provider_failure_not_empty_success(self):
        data_cases = [self.treg(output={}), self.treg(_treg={}), self.treg(rows=[{}]),
                      self.treg(rows=[None]), self.treg(rows=[{}, {}]), {"error": "secret"}]
        for data in data_cases:
            with self.subTest(data=data), self.assertRaises(ProviderError) as caught:
                discover({"audience": "x"}, 1, {"provider": "treg", "token": "secret", "max_cost_usd": 1,
                                               "http": lambda *a: (200, {}, data)})
            self.assertNotIn("secret", str(caught.exception))
        for status in (301, 401, 402, 429, 503):
            with self.assertRaises(ProviderError) as caught:
                discover({"audience": "x"}, 1, {"provider": "treg", "token": "secret", "max_cost_usd": 1,
                                               "http": lambda *a: (status, {}, {"detail": "secret"})})
            self.assertNotIn("secret", str(caught.exception))

    def test_charge_over_cap_is_retained_for_ledger(self):
        result = discover({"audience": "x"}, 1, {"provider": "treg", "token": "secret", "max_cost_usd": .001,
                           "http": lambda *a: (200, {}, self.treg())})
        self.assertEqual(result["cost_usd"], .01)
        self.assertTrue(result["errors"])

    def test_duplicate_people_deduplicated(self):
        row = self.treg()["output"]["people"][0]
        result = discover({"audience": "x"}, 2, {"provider": "treg", "token": "secret", "max_cost_usd": 1,
                           "http": lambda *a: (200, {}, self.treg(rows=[row, row]))})
        self.assertEqual(len(result["prospects"]), 1)

    def test_keywords_preserve_current_catalogue_list_contract(self):
        calls = []
        def fake(*args):
            calls.append(args)
            return 200, {}, self.treg()
        config = {"provider": "treg", "token": "s", "max_cost_usd": 1, "http": fake,
                  "filters": {"title": "Founder", "keywords": ["operations", "automation"]}}
        discover({}, 1, config)
        self.assertEqual(calls[0][3]["keywords"], ["operations", "automation"])
        config["filters"]["keywords"] = "operations"
        with self.assertRaises(ProviderError):
            discover({}, 1, config)

    def test_fixture_conversation_stop_and_review(self):
        for text, intent in [("STOP!", "optout"), ("No thanks", "decline"), ("wrong person", "decline"),
                             ("yes", "interest"), ("schedule a meeting", "scheduling"), ("guarantee returns", "review")]:
            result = generate({}, {}, [{"role": "user", "text": text}], {"provider": "fixture"})
            self.assertEqual(result["intent"], intent)
            self.assertTrue(result["usage"]["synthetic"])

    def model_response(self, text=None):
        return {"choices": [{"finish_reason": "stop", "message": {"content": text or json.dumps({"text": "Could you clarify?", "intent": "review"})}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20}}

    def test_openai_request_and_price(self):
        calls = []
        def fake(*args):
            calls.append(args)
            return 200, {}, self.model_response()
        config = {"provider": "openai", "api_key": "test", "model": "chosen-model", "http": fake,
                  "input_usd_per_million": 2, "output_usd_per_million": 10}
        result = generate({"offer": "advice"}, {}, [], config)
        self.assertAlmostEqual(result["cost_usd"], .0004)
        self.assertEqual(calls[0][3]["model"], "chosen-model")
        self.assertNotIn("tools", calls[0][3])
        self.assertEqual(calls[0][3]["response_format"], {"type": "json_object"})

    def test_models_fail_closed_for_structured_output(self):
        for raw in ('not-json', '{}', '{"text":"", "intent":"reply"}',
                    '{"text":"ok", "intent":"send"}', '{"text":"ok", "intent":"reply", "send":true}',
                    '{"text":"ok", "intent":"reply", "intent":"review"}'):
            with self.assertRaises(ProviderError):
                generate({}, {}, [], {"provider": "openai", "api_key": "secret", "model": "m",
                                      "http": lambda *a: (200, {}, self.model_response(raw))})

    def test_anthropic_wire_and_unknown_cost(self):
        calls = []
        def fake(*args):
            calls.append(args)
            return 200, {}, {"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"text":"Could you clarify?","intent":"review"}'}],
                             "usage": {"input_tokens": 100, "output_tokens": 20}}
        result = generate({}, {}, [], {"provider": "anthropic", "api_key": "test", "model": "chosen", "http": fake})
        self.assertIsNone(result["cost_usd"])
        self.assertEqual(calls[0][2]["anthropic-version"], "2023-06-01")
        self.assertIn("system", calls[0][3])

    def test_model_no_implicit_credentials(self):
        with self.assertRaises(ProviderError):
            generate({}, {}, [], {"provider": "openai", "model": "m"})

    def test_model_truncation_tool_output_and_usage_errors(self):
        for change in ("length", "tool_calls", "bad_usage"):
            data = self.model_response()
            if change == "length":
                data["choices"][0]["finish_reason"] = "length"
            elif change == "tool_calls":
                data["choices"][0]["message"]["tool_calls"] = [{"name": "send"}]
            else:
                data["usage"]["prompt_tokens"] = -1
            with self.assertRaises(ProviderError):
                generate({}, {}, [], {"provider": "openai", "api_key": "s", "model": "m", "http": lambda *a: (200, {}, data)})

    def test_media_requires_review(self):
        with self.assertRaises(ProviderError):
            generate({}, {}, [{"role": "user", "text": None}], {"provider": "fixture"})

    def test_discovery_missing_cost_is_not_free(self):
        data = self.treg()
        del data["_treg"]["charged_micro"]
        with self.assertRaises(ProviderError):
            discover({"audience": "x"}, 1, {"provider": "treg", "token": "s", "max_cost_usd": 1, "http": lambda *a: (200, {}, data)})


class UnipileTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.identity = {"id": "account", "type": "WHATSAPP"}
        self.members = [{"account_id": "account", "is_self": 0, "provider_id": "27820000001@s.whatsapp.net"}]
        self.messages = [{"id": "m1", "is_sender": 0, "text": "Hello", "timestamp": "2020-01-01T00:00:00Z"}]
        self.hook = None
        self.client = UnipileClient(base_url="https://api1.unipile.com:13111/api/v1", api_key="secret", account_id="account", http=self.http)

    def http(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        path = urlsplit(url).path.removeprefix("/api/v1")
        query = parse_qs(urlsplit(url).query)
        if self.hook:
            answer = self.hook(path, query)
            if answer is not None:
                return 200, {}, answer
        if path == "/accounts/account":
            return 200, {}, self.identity
        self.assertEqual(query.get("account_id"), ["account"])
        if path.endswith("/attendees"):
            data = {"items": self.members}
        elif path.endswith("/messages"):
            data = {"items": self.messages}
        elif path == "/chats":
            data = {"items": [{"id": "chat", "account_id": "account"}]}
        else:
            data = {"id": "chat", "account_id": "account"}
        return 200, {}, data

    def test_verified_conversation_and_manual_unknown(self):
        self.messages.append({"id": "out", "is_sender": 1, "text": "answer", "timestamp": "2020-01-01T01:00:00Z"})
        result = self.client.fetch_conversation("chat")
        self.assertEqual(result["messages"][0]["sender_id"], self.members[0]["provider_id"])
        self.assertIsNone(result["messages"][1]["manual"])
        self.assertTrue(result["all_history"])
        self.assertFalse(self.client.verify_account()["delivery_verified"])
        self.assertEqual(len(self.client.list_chats()), 1)

    def test_identity_and_account_mismatch(self):
        for identity in ({}, {"id": "other", "type": "WHATSAPP"}, {"id": "account", "type": "LINKEDIN"}):
            self.identity = identity
            with self.assertRaises(ProviderError):
                self.client.fetch_conversation("chat")

    def test_bad_messages_refused(self):
        baseline = self.messages[0]
        for change in ({"is_sender": "0"}, {"id": None}, {"timestamp": "2020-01-01"},
                       {"timestamp": "2999-01-01T00:00:00Z"}, {"account_id": "other"}, {"chat_id": "other"}, {"text": 1}):
            self.messages = [{**baseline, **change}]
            with self.assertRaises(ProviderError):
                self.client.fetch_conversation("chat")
        self.messages = [baseline, baseline]
        with self.assertRaises(ProviderError):
            self.client.fetch_conversation("chat")

    def test_group_sender_not_invented_and_media_retained(self):
        self.members.append({"account_id": "account", "is_self": 0, "provider_id": "27820000002@s.whatsapp.net"})
        self.messages[0].update(text=None, sender_id="opaque", attachments=[{"type": "audio"}])
        result = self.client.fetch_conversation("chat")
        self.assertIsNone(result["messages"][0]["sender_id"])
        self.assertTrue(result["raw_messages"][0]["attachments"])

    def test_pagination_refuses_cycle_and_bad_shape(self):
        for page in ({}, {"items": [None]}, {"items": [], "cursor": "next"},
                     {"items": [{"id": "chat", "account_id": "account"}], "cursor": "cycle"}):
            self.hook = lambda path, query: page if path == "/chats" else None
            with self.assertRaises(ProviderError):
                self.client.list_chats()

    def test_url_and_path_boundaries(self):
        for base in ("http://api.unipile.com", "https://evil.invalid", "https://api.unipile.com.evil.invalid", "https://secret@api.unipile.com"):
            with self.assertRaises(ProviderError):
                UnipileClient(base_url=base, api_key="x", account_id="a")
        with self.assertRaises(ProviderError):
            self.client.fetch_conversation("../other")
        self.assertFalse(self.calls)

    def test_membership_drift_refused(self):
        reads = []
        def drift(path, query):
            if path.endswith("/attendees"):
                reads.append(path)
                if len(reads) == 2:
                    return {"items": [{"account_id": "account", "is_self": 0, "provider_id": "27820000002@s.whatsapp.net"}]}
        self.hook = drift
        with self.assertRaisesRegex(ProviderError, "changed"):
            self.client.fetch_conversation("chat")

    def test_page_bound_and_duplicate_chats(self):
        self.hook = lambda path, query: ({"items": [{"id": "chat", "account_id": "account"}],
                                         "cursor": str(int(query.get("cursor", ["0"])[0]) + 1)} if path == "/chats" else None)
        with self.assertRaisesRegex(ProviderError, "bound"):
            self.client.list_chats()
        self.hook = lambda path, query: {"items": [{"id": "chat", "account_id": "account"}] * 2} if path == "/chats" else None
        with self.assertRaisesRegex(ProviderError, "duplicate"):
            self.client.list_chats()


if __name__ == "__main__":
    unittest.main()

"""Synthetic responses follow publicly inspected phone route schema; no paid calls."""
import unittest

from concierge_service.enrichment import enrich
from concierge_service.providers import ProviderError


class EnrichmentTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.prospect = {"id": "p1", "name": "Alex Example", "company": "Example Company",
                         "profile_url": "https://www.linkedin.com/in/alex-example"}
        self.response = {"output": {"phone": "+27820000001", "line_type": "mobile"}, "raw": {},
                         "_treg": {"outcome": "hit", "charged_micro": 80000, "served_by": "aviato.people.phone.find"}}
        self.headers = {}
        self.config = {"provider": "treg", "token": "synthetic-secret", "max_cost_usd": .25, "http": self.http}

    def http(self, *args):
        self.calls.append(args)
        return 200, self.headers, self.response

    def test_exact_routed_request_and_unverified_result(self):
        result = enrich(self.prospect, self.config)
        self.assertEqual(self.calls[0][:2], ("POST", "https://treg.to/call/treg.people.phone.find"))
        self.assertEqual(self.calls[0][3], {"linkedin_url": self.prospect["profile_url"]})
        self.assertEqual(self.calls[0][2]["X-Treg-Route-Max-Cost"], "0.2500")
        self.assertEqual(self.calls[0][2]["X-Treg-Route-Strict-Filters"], "1")
        self.assertEqual(result["phone"], "+27820000001")
        self.assertEqual(result["phone_status"], "provider_unverified")
        self.assertEqual(result["cost_usd"], .08)
        self.assertFalse(result["evidence"]["ownership_verified"])
        self.assertEqual(result["evidence"]["requested_identity"]["company"], "Example Company")

    def test_name_company_domain_identity(self):
        del self.prospect["profile_url"]
        self.prospect["domain"] = "example.com"
        enrich(self.prospect, self.config)
        self.assertEqual(self.calls[0][3], {"domain": "example.com", "full_name": "Alex Example"})

    def test_identity_and_budget_required_before_call(self):
        for change in ({"profile_url": "https://example.com/person"}, {"profile_url": "https://linkedin.com/company/example"},
                       {"name": ""}, {"company": ""}, {"id": ""}):
            with self.assertRaises(ProviderError):
                enrich({**self.prospect, **change}, self.config)
        for change in ({"token": ""}, {"max_cost_usd": 0}, {"base_url": "https://evil.invalid"}):
            with self.assertRaises(ProviderError):
                enrich(self.prospect, {**self.config, **change})
        self.assertFalse(self.calls)

    def test_provider_format_is_not_country_guess(self):
        self.response["output"]["phone"] = "082 000 0001"
        result = enrich(self.prospect, self.config)
        self.assertIsNone(result["phone"])
        self.assertEqual(result["phone_status"], "unresolved_format")
        self.assertEqual(result["evidence"]["output"]["phone"], "082 000 0001")

    def test_miss_distinct_from_error(self):
        self.response["output"]["phone"] = None
        self.response["_treg"].update(outcome="miss", charged_micro=0)
        result = enrich(self.prospect, self.config)
        self.assertIsNone(result["phone"])
        self.assertEqual(result["phone_status"], "missing")
        self.assertEqual(result["cost_usd"], 0)
        self.response["output"] = {}
        with self.assertRaises(ProviderError):
            enrich(self.prospect, self.config)

    def test_dnc_and_ignored_identity_filters_do_not_return_phone(self):
        self.response["raw"] = {"results": [{"phones": [{"doNotCall": True}]}]}
        result = enrich(self.prospect, self.config)
        self.assertIsNone(result["phone"])
        self.assertEqual(result["phone_status"], "do_not_call")
        self.response["raw"] = {}
        self.headers["X-Treg-Ignored-Filters"] = "full_name"
        self.assertIsNone(enrich(self.prospect, self.config)["phone"])

    def test_cost_header_actual_overcap_and_unknown_settlement(self):
        self.headers["X-Treg-Cost-Micro"] = "500000"
        result = enrich(self.prospect, self.config)
        self.assertEqual(result["cost_usd"], .5)
        self.assertTrue(result["errors"])
        self.headers.clear()
        del self.response["_treg"]["charged_micro"]
        with self.assertRaises(ProviderError):
            enrich(self.prospect, self.config)

    def test_no_secrets_in_error(self):
        def failed(*args):
            raise RuntimeError("synthetic-secret")
        with self.assertRaises(ProviderError) as error:
            enrich(self.prospect, {**self.config, "http": failed})
        self.assertNotIn("synthetic-secret", str(error.exception))

    def test_fixture_never_manufactures_a_phone(self):
        result = enrich({}, {"provider": "fixture"})
        self.assertIsNone(result["phone"])
        self.assertTrue(result["evidence"]["synthetic"])


if __name__ == "__main__":
    unittest.main()

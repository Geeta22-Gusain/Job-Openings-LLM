import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import job_providers as providers
import job_search as js


def options(**changes):
    values = dict(location="India", roles=["qa", "program-manager"], pages=2,
                  providers=["adzuna", "remotive"])
    values.update(changes)
    return argparse.Namespace(**values)


class ProviderTests(unittest.TestCase):
    def test_adzuna_normalization_and_country_query(self):
        request = Mock(return_value={"results": [{"id": "123", "title": "QA Lead",
            "redirect_url": "https://www.adzuna.in/details/123", "description": "<p>8-12 years Java</p>",
            "company": {"display_name": "Example"}, "location": {"display_name": "India"},
            "salary_min": 1500000, "salary_is_predicted": "1", "created": "2026-10-18"}]})
        with patch.dict("os.environ", {"ADZUNA_APP_ID": "test-id", "ADZUNA_APP_KEY": "test-key"}):
            records = providers.AdzunaProvider.search(options(), request)
        self.assertEqual(request.call_count, 2)  # one short page per role
        self.assertEqual(records[0]["company"], "Example")
        self.assertNotIn("<p>", records[0]["description"])
        self.assertEqual(records[0]["provider"], "adzuna")
        self.assertEqual(json.loads(records[0]["salary"])["salary_is_predicted"], "1")
        params = parse_qs(urlsplit(request.call_args.args[0]).query)
        self.assertNotIn("where", params)
        self.assertIn("/jobs/in/", request.call_args.args[0])

    def test_adzuna_pagination_and_city(self):
        request = Mock(side_effect=[{"results": [{}] * 50}, {"results": []}])
        with patch.dict("os.environ", {"ADZUNA_APP_ID": "test-id", "ADZUNA_APP_KEY": "test-key"}):
            self.assertEqual(providers.AdzunaProvider.search(options(roles=["qa"], location="Pune"), request), [])
        self.assertIn("/search/2?", request.call_args.args[0])
        self.assertEqual(parse_qs(urlsplit(request.call_args.args[0]).query)["where"], ["Pune"])

    def test_missing_credentials_no_request(self):
        request = Mock()
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(providers.ProviderConfigurationError):
            providers.AdzunaProvider.search(options(), request)
        request.assert_not_called()

    def test_remotive_filters_role_location_and_attribution(self):
        jobs = [{"id": i, "title": title, "candidate_required_location": location,
                 "url": f"https://remotive.com/remote-jobs/{i}", "description": "<p>10 years Scrum</p>"}
                for i, (title, location) in enumerate([
                    ("QA Lead", "India"), ("Program Manager", "Worldwide"),
                    ("QA Lead", "USA only"), ("Sales Manager", "India"), ("QA Lead", "")])]
        request = Mock(return_value={"jobs": jobs})
        records = providers.RemotiveProvider.search(options(), request)
        self.assertEqual(len(records), 2)
        request.assert_called_once()
        self.assertEqual(records[0]["provider"], "remotive")
        self.assertEqual(records[0]["work_mode"], "Remote")
        self.assertIn("Remotive", records[0]["provider_warnings"][0])

    def test_remotive_city_not_silently_ignored(self):
        request = Mock()
        with self.assertRaises(providers.ProviderConfigurationError):
            providers.RemotiveProvider.search(options(location="Pune"), request)
        request.assert_not_called()

    def test_schema_errors_not_empty_success(self):
        with self.assertRaises(ValueError):
            providers.RemotiveProvider.search(options(), Mock(return_value={"error": "unavailable"}))

    def test_cli_partial_failure_retains_results_and_report(self):
        listing = {"url": "https://remotive.com/remote-jobs/1", "title": "QA Lead",
                   "description": "8-12 years Java", "provider": "remotive", "provider_job_id": "1"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {}, clear=True), \
                patch.object(providers.RemotiveProvider, "search", return_value=[listing]):
            code = js.main(["--providers", "adzuna", "remotive", "--output", tmp])
            self.assertEqual(code, 2)
            report = json.loads((Path(tmp) / "providers.json").read_text())
            self.assertEqual([p["status"] for p in report], ["failed", "ok"])
            jobs = json.loads((Path(tmp) / "jobs.json").read_text())
            self.assertEqual(jobs[0]["provider"], "remotive")
            self.assertEqual(jobs[0]["provider_job_id"], "1")

    def test_all_failed_exit_code_and_secret_redaction(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(providers.RemotiveProvider, "search", side_effect=ValueError("secret-in-url")):
            self.assertEqual(js.main(["--providers", "remotive", "--output", tmp]), 1)
            report = (Path(tmp) / "providers.json").read_text()
            self.assertNotIn("secret-in-url", report)
            self.assertEqual(json.loads((Path(tmp) / "jobs.json").read_text()), [])


if __name__ == "__main__":
    unittest.main()

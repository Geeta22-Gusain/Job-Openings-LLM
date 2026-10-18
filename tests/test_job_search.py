import argparse
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import job_search as js


def options(**changes):
    values = dict(fetch=False, llm=False, model="test", min_experience=8,
                  max_experience=12, roles=["qa", "program-manager"])
    values.update(changes)
    return argparse.Namespace(**values)


class JobSearchTests(unittest.TestCase):
    def test_qa_skills_and_range(self):
        job = js.process({"title": "Senior QA Engineer", "description":
            "8-12 years. Java Selenium Scrum functional testing API testing Cursor Claude "
            "resource planning sprint planning sprint deliverables", "url": "https://example.com/jobs/1"}, options())
        self.assertEqual(job["review_status"], "potential_match")
        self.assertEqual(job["skill_score"], 100)
        self.assertEqual(job["experience_min"], 8)
        self.assertEqual(job["experience_max"], 12)

    def test_manager_without_qa_tools(self):
        job = js.process({"title": "Program Manager", "description":
            "10+ years; resource allocation, sprint planning and Scrum."}, options())
        self.assertEqual(job["role"], "program-manager")
        self.assertEqual(job["review_status"], "potential_match")
        self.assertIsNone(job["experience_max"])
        self.assertIn("Java", job["missing_skills"])

    def test_missing_and_outside_experience(self):
        for text, status in [("Senior Java Selenium", "needs_review"),
                             ("15-20 years", "excluded"), ("3 to 5 years", "excluded")]:
            with self.subTest(text=text):
                job = js.process({"title": "QA Engineer", "description": text}, options())
                self.assertEqual(job["review_status"], status)

    def test_unrelated_role(self):
        job = js.process({"title": "Sales Director", "description": "8-12 years"}, options())
        self.assertEqual(job["review_status"], "needs_review")
        self.assertEqual(job["role"], "unknown")

    def test_jsonld_public_page(self):
        page = '<script type="application/ld+json">' + json.dumps({"@graph": [{
            "@type": "JobPosting", "title": "QA Lead", "hiringOrganization": {"name": "Example"},
            "jobLocation": {"address": {"addressLocality": "Bengaluru", "addressCountry": "India"}},
            "description": "<p>8–12 years Java Selenium</p>", "datePosted": "2026-10-01"}]}) + '</script>'
        with patch.object(js, "fetch_page", return_value=page):
            job = js.process({"url": "https://example.com/jobs/1"}, options(fetch=True))
        self.assertEqual(job["company"], "Example")
        self.assertEqual(job["location"], "Bengaluru, India")
        self.assertEqual(job["review_status"], "potential_match")
        self.assertEqual(job["extraction_method"], "json_ld")

    def test_blocked_page_retains_snippet(self):
        with patch.object(js, "fetch_page", side_effect=OSError("blocked")):
            job = js.process({"url": "https://www.linkedin.com/jobs/view/1", "search_title": "QA Lead",
                              "snippet": "8-12 years Java"}, options(fetch=True))
        self.assertEqual(job["review_status"], "needs_review")
        self.assertTrue(job["warnings"])
        self.assertEqual(job["source"], "linkedin")

    def test_llm_and_failure(self):
        record = {"title": "QA Lead", "description": "8-12 years Java"}
        with patch.object(js, "llm_extract", return_value={"company": "Example", "experience_min": 8, "experience_max": 12}):
            job = js.process(record, options(llm=True))
        self.assertEqual(job["company"], "Example")
        self.assertEqual(job["extraction_method"], "llm")
        with patch.object(js, "llm_extract", side_effect=RuntimeError("unavailable")):
            job = js.process(record, options(llm=True))
        self.assertTrue(job["warnings"])
        self.assertEqual(job["title"], "QA Lead")

    def test_index_is_not_a_match(self):
        nodes = [{"@type": "JobPosting", "title": "QA Lead"}] * 2
        with patch.object(js, "fetch_page", return_value='<script type="application/ld+json">' + json.dumps(nodes) + '</script>'):
            job = js.process({"url": "https://example.com/jobs", "title": "QA Lead", "description": "8-12 years"}, options(fetch=True))
        self.assertEqual(job["review_status"], "needs_review")

    def test_search_queries_and_deduplication(self):
        args = options(location="India", sources=["naukri", "linkedin", "company"], pages=1, freshness="m")
        with patch.dict("os.environ", {"SERPAPI_API_KEY": "test"}), patch.object(js, "request_json", return_value={
            "organic_results": [{"title": "QA Lead", "link": "https://example.com/job/1?utm_source=google", "snippet": "8-12 years"}]
        }) as request:
            records = js.discover(args)
        self.assertEqual(request.call_count, 6)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["url"], "https://example.com/job/1")

    def test_cli_exports_and_formula_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [{"title": "QA Lead", "company": "=UNTRUSTED()", "description": "8-12 years Java Selenium",
                        "url": "https://example.com/job/1"}] * 2
            (root / "input.json").write_text(json.dumps(records))
            self.assertEqual(js.main(["--input", str(root / "input.json"), "--output", str(root / "output")]), 0)
            jobs = json.loads((root / "output/jobs.json").read_text())
            self.assertEqual(len(jobs), 1)
            with (root / "output/jobs.csv").open() as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["company"], "'=UNTRUSTED()")


if __name__ == "__main__":
    unittest.main()

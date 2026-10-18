"""Job API plugins. Each search(args, request_json) returns normalized listing dicts.

Plugins receive the shared HTTPS JSON client to keep retries/TLS behavior consistent
and allow offline contract tests. Register additional plugins in PROVIDERS.
"""
import html
import json
import os
import re
from urllib.parse import urlencode


class ProviderConfigurationError(ValueError):
    """Safe, actionable configuration error containing no credential values."""


def text(value):
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def items(response, key):
    if not isinstance(response, dict) or not isinstance(response.get(key), list):
        raise ValueError("Unexpected provider response schema")
    if any(not isinstance(item, dict) for item in response[key]):
        raise ValueError("Unexpected provider listing schema")
    return response[key]


class AdzunaProvider:
    """Official Adzuna API, India country endpoint by default."""
    @staticmethod
    def search(args, request_json):
        app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
        if not app_id or not app_key:
            raise ProviderConfigurationError("Set ADZUNA_APP_ID and ADZUNA_APP_KEY for Adzuna.")
        records = []
        for role in args.roles:
            for page in range(1, args.pages + 1):
                params = {"app_id": app_id, "app_key": app_key, "results_per_page": 50,
                          "what": "QA" if role == "qa" else "program manager",
                          "sort_by": "date", "content-type": "application/json"}
                # India is the endpoint country, not an Adzuna city/region query.
                if args.location.casefold() != "india":
                    params["where"] = args.location
                response = request_json(f"https://api.adzuna.com/v1/api/jobs/in/search/{page}?" + urlencode(params))
                results = items(response, "results")
                for item in results:
                    url = item.get("redirect_url")
                    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                        continue
                    salary = {k: item[k] for k in ("salary_min", "salary_max", "salary_is_predicted") if item.get(k) is not None}
                    records.append({"url": url, "apply_url": url, "provider": "adzuna",
                        "provider_job_id": str(item.get("id", "")),
                        "title": text(item.get("title")),
                        "company": text((item.get("company") or {}).get("display_name")),
                        "location": text((item.get("location") or {}).get("display_name")),
                        "description": text(item.get("description")),
                        "salary": json.dumps(salary) if salary else None,
                        "employment_type": " / ".join(text(item.get(k)) for k in ("contract_type", "contract_time") if item.get(k)),
                        "posted_date": item.get("created"), "search_role": role,
                        "provider_warnings": ["Adzuna descriptions may be truncated; verify full details and salary units on the original listing."]})
                if len(results) < 50:
                    break
        return records


def india_eligible(location):
    """Conservative text check; eligibility still needs confirmation with employer."""
    value = location.casefold().strip()
    return bool(re.search(r"\bindia\b|\bworldwide\b|\banywhere\b", value)) or value in {"global", "world"}


class RemotiveProvider:
    """Public remote-jobs API. No key required; preserve Remotive attribution."""
    @staticmethod
    def search(args, request_json):
        if args.location.casefold() != "india":
            raise ProviderConfigurationError("Remotive currently supports --location India only; remote city eligibility is not inferred.")
        # One request for all categories avoids per-role polling/rate pressure.
        # Remotive recommends querying at most four times per day. Cache externally
        # when scheduling; --pages has no effect on this unpaginated endpoint.
        results = items(request_json("https://remotive.com/api/remote-jobs"), "jobs")
        records = []
        for item in results:
            title = text(item.get("title"))
            qa = re.search(r"\b(qa|sdet|quality assurance|test(?:ing)? (?:engineer|lead|manager|automation))\b", title, re.I)
            manager = re.search(r"\bprogram(?:me)? manager\b", title, re.I)
            role = "program-manager" if manager else "qa" if qa else None
            if role not in args.roles:
                continue
            location = text(item.get("candidate_required_location"))
            # This plugin deliberately supports India, not arbitrary geographic inference.
            if not india_eligible(location):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                continue
            records.append({"url": url, "apply_url": url, "provider": "remotive",
                "provider_job_id": str(item.get("id", "")), "title": title,
                "company": text(item.get("company_name")), "location": location,
                "description": text(item.get("description")), "salary": text(item.get("salary")) or None,
                "employment_type": text(item.get("job_type")), "work_mode": "Remote",
                "posted_date": item.get("publication_date"), "search_role": role,
                "provider_warnings": ["Source: Remotive. Confirm India eligibility with the employer; remote does not mean eligible everywhere."]})
        return records


PROVIDERS = {"adzuna": AdzunaProvider, "remotive": RemotiveProvider}

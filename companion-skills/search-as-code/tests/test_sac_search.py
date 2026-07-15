import importlib.util
import io
import json
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sac_search.py"
spec = importlib.util.spec_from_file_location("sac_search", SCRIPT)
sac_search = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(sac_search)


def valid_plan():
    return {
        "topic": "Perplexity docs",
        "mode": "standard",
        "queries": [
            {
                "query": "site:docs.perplexity.ai Search API pricing",
                "purpose": "api-docs",
                "search_domain_filter": ["docs.perplexity.ai"],
                "max_results": 10,
                "snippet_mode": "high",
                "priority": 1,
            },
            {
                "query": "site:docs.perplexity.ai Agent API sandbox",
                "purpose": "api-docs",
                "search_domain_filter": ["docs.perplexity.ai"],
                "max_results": 10,
                "snippet_mode": "high",
                "priority": 2,
            },
        ],
    }


class SacSearchTests(unittest.TestCase):
    def test_validate_plan_rejects_missing_fields(self):
        errors = sac_search.validate_plan({"topic": "", "mode": "bad", "queries": []})
        self.assertIn("topic must be a non-empty string", errors)
        self.assertTrue(any("mode must be" in error for error in errors))
        self.assertIn("queries must be a non-empty array", errors)

    def test_validate_plan_rejects_unknown_fields_and_bad_query_type(self):
        plan = {
            "topic": "bad schema",
            "mode": "standard",
            "generated_at": "2026-07-08T00:00:00Z",
            "queries": [
                {
                    "query": "example",
                    "purpose": "x",
                    "query_type": "banana",
                    "max_result": 10,
                }
            ],
        }

        errors = sac_search.validate_plan(plan)

        self.assertTrue(any("unsupported fields" in error and "generated_at" in error for error in errors))
        self.assertTrue(any("query_type" in error and "banana" in error for error in errors))
        self.assertTrue(any("unsupported fields" in error and "max_result" in error for error in errors))

    def test_validate_plan_rejects_mixed_domain_filter_modes(self):
        plan = {
            "topic": "mixed filter",
            "mode": "standard",
            "queries": [
                {
                    "query": "example",
                    "purpose": "x",
                    "search_domain_filter": ["sec.gov", "-fool.com"],
                }
            ],
        }

        errors = sac_search.validate_plan(plan)

        self.assertTrue(any("allowlist or denylist" in error for error in errors))

    def test_batching_groups_compatible_queries_in_one_request(self):
        batches = sac_search.build_batches(valid_plan()["queries"])
        self.assertEqual(len(batches), 1)
        self.assertIsInstance(batches[0]["body"]["query"], list)
        self.assertEqual(len(batches[0]["body"]["query"]), 2)

    def test_canonical_url_removes_tracking_params(self):
        canon = sac_search.canonical_url("HTTPS://Example.COM/path/?utm_source=x&a=1#frag")
        self.assertEqual(canon, "https://example.com/path?a=1")

    def test_canonical_url_collapses_www_host(self):
        self.assertEqual(
            sac_search.canonical_url("https://www.example.com/path?utm_source=x"),
            "https://example.com/path",
        )

    def test_run_plan_writes_ledgers_with_mocked_api(self):
        def fake_key():
            return "test-key"

        def fake_fetch(body, api_key, timeout=60.0):
            self.assertEqual(api_key, "test-key")
            return {
                "results": [
                    {
                        "title": "Perplexity Search API",
                        "url": "https://docs.perplexity.ai/docs/search/quickstart?utm_source=test",
                        "snippet": "Search API returns ranked web results.",
                        "date": "2026-06-01",
                    },
                    {
                        "title": "Perplexity Search API duplicate",
                        "url": "https://docs.perplexity.ai/docs/search/quickstart",
                        "snippet": "A longer Search API snippet that should be retained by dedupe.",
                        "date": "2026-06-01",
                    },
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(sac_search, "get_api_key", fake_key), mock.patch.object(sac_search, "fetch_search", fake_fetch):
                sac_search.run_plan(valid_plan(), tmp_path, concurrency=1, timeout=1)

            sources = [json.loads(line) for line in (tmp_path / "sources.jsonl").read_text().splitlines()]
            evidence = [json.loads(line) for line in (tmp_path / "evidence.jsonl").read_text().splitlines()]
            costs = [json.loads(line) for line in (tmp_path / "costs.jsonl").read_text().splitlines()]

            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["canonical_url"], "https://docs.perplexity.ai/docs/search/quickstart")
            self.assertIn("longer Search API snippet", evidence[0]["evidence_quote"])
            self.assertEqual(sum(row["logical_query_count"] for row in costs), 2)
            self.assertEqual(sum(row["http_request_count"] for row in costs), 2)
            self.assertEqual(sum(row["estimated_cost_usd"] for row in costs), 0.01)
            self.assertTrue((tmp_path / "coverage_summary.md").exists())
            self.assertTrue((tmp_path / "plan_quality.json").exists())
            self.assertTrue((tmp_path / "coverage_diagnostics.json").exists())

    def test_run_plan_defaults_to_one_query_per_request(self):
        calls = []

        def fake_fetch(body, api_key, timeout=60.0):
            calls.append(body["query"])
            return {
                "results": [
                    {
                        "title": f"Result for {body['query']}",
                        "url": f"https://docs.perplexity.ai/{len(calls)}",
                        "snippet": "Search API result.",
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(sac_search, "get_api_key", lambda: "k"), mock.patch.object(sac_search, "fetch_search", fake_fetch):
                sac_search.run_plan(valid_plan(), tmp_path, concurrency=2, timeout=1)

            manifest = json.loads((tmp_path / "run_manifest.json").read_text())
            costs = [json.loads(line) for line in (tmp_path / "costs.jsonl").read_text().splitlines()]

        self.assertEqual(len(calls), 2)
        self.assertTrue(manifest["no_batch"])
        self.assertEqual(manifest["http_request_count"], 2)
        self.assertEqual([row["logical_query_count"] for row in costs], [1, 1])

    def test_run_plan_persists_partial_results_and_errors_without_wiping_prior_ledgers(self):
        def fake_fetch(body, api_key, timeout=60.0):
            if "Agent API" in body["query"]:
                raise RuntimeError("Perplexity request failed: 500 server error")
            return {
                "results": [
                    {
                        "title": "Perplexity Search API",
                        "url": "https://docs.perplexity.ai/search",
                        "snippet": "Search API returns ranked web results.",
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "results.jsonl").write_text(json.dumps({"sentinel": True}) + "\n")
            with mock.patch.object(sac_search, "get_api_key", lambda: "k"), mock.patch.object(sac_search, "fetch_search", fake_fetch):
                sac_search.run_plan(valid_plan(), tmp_path, concurrency=2, timeout=1)

            result_rows = [json.loads(line) for line in (tmp_path / "results.jsonl").read_text().splitlines() if line.strip()]
            errors = [json.loads(line) for line in (tmp_path / "errors.jsonl").read_text().splitlines() if line.strip()]
            sources = [json.loads(line) for line in (tmp_path / "sources.jsonl").read_text().splitlines() if line.strip()]

        self.assertTrue(any(row.get("sentinel") for row in result_rows))
        self.assertEqual(len(errors), 1)
        self.assertIn("q0002", errors[0]["query_ids"])
        self.assertEqual(len(sources), 1)

    def test_flat_multi_query_batch_does_not_attribute_result_to_all_queries(self):
        batch = sac_search.build_batches(valid_plan()["queries"])[0]
        rows = sac_search.flatten_results(
            {"results": [{"title": "Flat result", "url": "https://example.com/a", "snippet": "flat shape"}]},
            batch,
        )

        self.assertEqual(rows[0]["_matched_query_ids"], [])
        self.assertEqual(rows[0]["_batch_attribution_error"], "flat_multi_query_response")

    def test_run_plan_logs_flat_batch_attribution_warning_to_errors_ledger(self):
        def fake_fetch(body, api_key, timeout=60.0):
            self.assertIsInstance(body["query"], list)
            return {
                "results": [
                    {
                        "title": "Flat batch result",
                        "url": "https://docs.perplexity.ai/flat",
                        "snippet": "A flat multi-query response shape.",
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(sac_search, "get_api_key", lambda: "k"), mock.patch.object(sac_search, "fetch_search", fake_fetch):
                sac_search.run_plan(valid_plan(), tmp_path, concurrency=1, timeout=1, no_batch=False)

            errors = [json.loads(line) for line in (tmp_path / "errors.jsonl").read_text().splitlines() if line.strip()]
            sources = [json.loads(line) for line in (tmp_path / "sources.jsonl").read_text().splitlines() if line.strip()]

        self.assertEqual(errors[0]["error_type"], "BatchAttributionWarning")
        self.assertIn("flat_multi_query_response", errors[0]["error"])
        self.assertEqual(sources[0]["matched_query_ids"], [])

    def test_grouped_batch_shape_mismatch_is_rejected(self):
        batch = sac_search.build_batches(valid_plan()["queries"])[0]
        with self.assertRaisesRegex(ValueError, "group count"):
            sac_search.flatten_results({"results": [{"results": []}]}, batch)

    def test_costs_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "costs.jsonl").write_text(
                json.dumps({"http_request_count": 1, "logical_query_count": 2, "estimated_cost_usd": 0.005}) + "\n"
            )
            out = io.StringIO()
            with redirect_stdout(out):
                sac_search.print_costs(tmp_path)
            captured = json.loads(out.getvalue())
            self.assertEqual(captured, {"estimated_cost_usd": 0.005, "http_request_count": 1, "logical_query_count": 2})


class SacSearchFeatureTests(unittest.TestCase):
    def test_no_batch_one_query_per_request(self):
        batches = sac_search.build_batches(valid_plan()["queries"], no_batch=True)
        self.assertEqual(len(batches), 2)
        for batch in batches:
            self.assertIsInstance(batch["body"]["query"], str)

    def test_tier_for_url(self):
        self.assertEqual(sac_search.tier_for_url("https://www.sec.gov/edgar"), 1)
        self.assertEqual(sac_search.tier_for_url("https://ir.acme.com/news"), 1)
        self.assertEqual(sac_search.tier_for_url("https://seekingalpha.com/article/x"), 4)
        self.assertEqual(sac_search.tier_for_url("https://reuters.com/markets"), 2)
        self.assertEqual(sac_search.tier_for_url("https://a-random-blog.example/post"), 3)
        self.assertEqual(sac_search.tier_for_url("https://cdc.gov/x"), 1)
        self.assertEqual(sac_search.tier_for_url("https://www.harvard.edu/x"), 2)
        self.assertEqual(sac_search.tier_for_url("https://news.acme.co/x", ["acme.co"]), 1)

    def test_source_type_for(self):
        self.assertEqual(sac_search.source_type_for("https://www.sec.gov/x", 1), "sec_filing")
        self.assertEqual(sac_search.source_type_for("https://ir.acme.com/x", 1), "company_ir")
        self.assertEqual(sac_search.source_type_for("https://reuters.com/x", 2), "news")
        self.assertEqual(sac_search.source_type_for("https://www.reuters.com/x", 2), "news")
        self.assertEqual(sac_search.source_type_for("https://random.example/x", 3), "web")

    def test_query_type_filter_injection(self):
        queries = [
            {"query": "q1", "purpose": "p", "query_type": "filings"},
            {"query": "q2", "purpose": "p", "query_type": "filings", "search_domain_filter": ["example.com"]},
            {"query": "q3", "purpose": "p"},
        ]
        out, applied = sac_search.apply_query_type_filters(queries)
        self.assertEqual(applied, 1)
        self.assertIn("sec.gov", out[0]["search_domain_filter"])
        self.assertFalse(
            any(item.startswith("-") for item in out[0]["search_domain_filter"]),
            "query_type-injected filters must use allowlist or denylist mode, not both",
        )
        self.assertEqual(out[1]["search_domain_filter"], ["example.com"])
        self.assertNotIn("search_domain_filter", out[2])

    def test_query_type_filter_injection_includes_issuer_domains_without_mixed_modes(self):
        queries = [{"query": "q1", "purpose": "p", "query_type": "results_earnings"}]
        out, applied = sac_search.apply_query_type_filters(queries, issuer_domains=["microsoft.com", "ir.microsoft.com"])

        self.assertEqual(applied, 1)
        flt = out[0]["search_domain_filter"]
        self.assertIn("microsoft.com", flt)
        self.assertIn("ir.microsoft.com", flt)
        self.assertFalse(any(item.startswith("-") for item in flt))

    def test_collision_flags(self):
        wrong = {"title": "Apple posts record quarter", "snippet": "iphone sales", "url": "https://x.com/a"}
        flags = sac_search.collision_flags(wrong, entity="Zentalis Pharmaceuticals", ticker="ZNTL")
        self.assertIn("entity_name_absent", flags)
        self.assertIn("ticker_absent", flags)
        right = {"title": "Zentalis ZNTL reports trial data", "snippet": "results", "url": "https://sec.gov/z"}
        self.assertEqual(sac_search.collision_flags(right, entity="Zentalis Pharmaceuticals", ticker="ZNTL"), [])

    def test_choose_extract_snippet(self):
        text = "intro text and then the important passage about revenue growth and margins"
        picked = sac_search.choose_extract_snippet(text, ["revenue"], None)
        self.assertIn("revenue", picked["snippet"].lower())
        self.assertTrue(picked["locator"].startswith("char_span:"))
        self.assertIn("span_start", picked)
        self.assertIn("span_end", picked)
        pages = ["first page content here", "second page revenue growth details"]
        picked2 = sac_search.choose_extract_snippet(" ".join(pages), ["revenue"], pages)
        self.assertTrue(picked2["locator"].startswith("page:"))

    def test_fetch_url_bytes_rejects_unsafe_urls_before_fetch(self):
        for url in ("file:///etc/passwd", "http://127.0.0.1:8080/x", "http://169.254.169.254/latest/meta-data"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    sac_search.fetch_url_bytes(url, timeout=1)

    def test_fetch_url_bytes_rejects_private_dns_resolution(self):
        addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]
        with mock.patch.object(sac_search.socket, "getaddrinfo", return_value=addrinfo):
            with self.assertRaises(ValueError):
                sac_search.fetch_url_bytes("https://example.com/private", timeout=1)

    def test_build_stock_plan_is_valid(self):
        plan = sac_search.build_stock_plan("Microsoft Corporation", "MSFT", exchange="NASDAQ", issuer_domains=["microsoft.com"])
        self.assertEqual(sac_search.validate_plan(plan), [])
        self.assertEqual(plan["entity"], "Microsoft Corporation")
        self.assertEqual(plan["ticker"], "MSFT")
        self.assertEqual(plan["issuer_domains"], ["microsoft.com"])
        self.assertTrue(all("query_type" in q for q in plan["queries"]))
        self.assertTrue(any(q["query_type"] == "filings" for q in plan["queries"]))
        self.assertTrue(any(q["query_type"] == "issuer_ir" for q in plan["queries"]))
        self.assertTrue(any(q["query_type"] == "bear_case" for q in plan["queries"]))

    def test_run_plan_excludes_ticker_collision(self):
        plan = {
            "topic": "collision test",
            "mode": "standard",
            "entity": "Tesla Motors",
            "ticker": "TSLA",
            "queries": [{"query": "tesla earnings", "purpose": "x", "priority": 1}],
        }

        def fake_fetch(body, api_key, timeout=60.0):
            return {"results": [{"title": "Perplexity API docs", "url": "https://docs.perplexity.ai/x", "snippet": "unrelated content"}]}

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(sac_search, "get_api_key", lambda: "k"), mock.patch.object(sac_search, "fetch_search", fake_fetch):
                sac_search.run_plan(plan, tmp_path, concurrency=1, timeout=1)
            sources = [line for line in (tmp_path / "sources.jsonl").read_text().splitlines() if line.strip()]
            excluded = [json.loads(line) for line in (tmp_path / "exclusion_log.jsonl").read_text().splitlines() if line.strip()]
            self.assertEqual(len(sources), 0)
            self.assertTrue(any("ticker_collision" in row.get("exclude_reason", "") for row in excluded))

    def test_entity_name_absent_is_not_fatal_when_ticker_matches(self):
        plan = {
            "topic": "ticker rescue test",
            "mode": "standard",
            "entity": "Microsoft Corporation",
            "ticker": "MSFT",
            "queries": [{"query": "microsoft earnings", "purpose": "x", "priority": 1}],
        }

        def fake_fetch(body, api_key, timeout=60.0):
            return {
                "results": [
                    {
                        "title": "MSFT earnings beat expectations",
                        "url": "https://www.reuters.com/markets/msft",
                        "snippet": "MSFT revenue grew.",
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(sac_search, "get_api_key", lambda: "k"), mock.patch.object(sac_search, "fetch_search", fake_fetch):
                sac_search.run_plan(plan, tmp_path, concurrency=1, timeout=1)
            sources = [json.loads(line) for line in (tmp_path / "sources.jsonl").read_text().splitlines() if line.strip()]
            excluded = [json.loads(line) for line in (tmp_path / "exclusion_log.jsonl").read_text().splitlines() if line.strip()]

        self.assertEqual(len(sources), 1)
        self.assertEqual(excluded, [])

    def test_tier_one_result_is_not_excluded_for_entity_name_absent(self):
        plan = {
            "topic": "tier one rescue test",
            "mode": "standard",
            "entity": "Tesla Motors",
            "ticker": "TSLA",
            "queries": [{"query": "tesla filing", "purpose": "x", "priority": 1}],
        }

        def fake_fetch(body, api_key, timeout=60.0):
            return {
                "results": [
                    {
                        "title": "Current report",
                        "url": "https://www.sec.gov/Archives/edgar/data/1",
                        "snippet": "Current report details.",
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(sac_search, "get_api_key", lambda: "k"), mock.patch.object(sac_search, "fetch_search", fake_fetch):
                sac_search.run_plan(plan, tmp_path, concurrency=1, timeout=1)
            sources = [json.loads(line) for line in (tmp_path / "sources.jsonl").read_text().splitlines() if line.strip()]

        self.assertEqual(len(sources), 1)

    def test_run_plan_tags_source_tier(self):
        def fake_fetch(body, api_key, timeout=60.0):
            return {"results": [{"title": "SEC filing", "url": "https://www.sec.gov/edgar/abc", "snippet": "annual report"}]}

        plan = {"topic": "tier test", "mode": "standard", "queries": [{"query": "x", "purpose": "y"}]}
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(sac_search, "get_api_key", lambda: "k"), mock.patch.object(sac_search, "fetch_search", fake_fetch):
                sac_search.run_plan(plan, tmp_path, concurrency=1, timeout=1)
            sources = [json.loads(line) for line in (tmp_path / "sources.jsonl").read_text().splitlines() if line.strip()]
            self.assertEqual(sources[0]["tier"], 1)
            self.assertEqual(sources[0]["source_tier"], "primary")
            self.assertFalse(sources[0]["hypothesis_only"])

    def test_plan_quality_warns_on_deep_plan_without_lanes(self):
        plan = {
            "topic": "Example technology deep dive",
            "mode": "ultradeep",
            "queries": [
                {"query": "example technology overview", "purpose": "overview", "max_results": 5},
                {"query": "example technology overview", "purpose": "overview", "max_results": 5},
                {"query": "example technology market", "purpose": "overview", "max_results": 5},
                {"query": "example technology products", "purpose": "overview", "max_results": 5},
                {"query": "example technology adoption", "purpose": "overview", "max_results": 5},
            ],
        }
        quality = sac_search.verify_plan_quality(plan)
        codes = {issue["code"] for issue in quality["issues"]}
        self.assertEqual(quality["status"], "warn")
        self.assertIn("duplicate_queries", codes)
        self.assertIn("low_purpose_diversity", codes)
        self.assertIn("missing_counterevidence_lane", codes)
        self.assertIn("missing_official_source_lane", codes)

    def test_low_information_extract_is_filtered(self):
        source = {
            "source_id": "src_low",
            "url": "https://example.com/news",
            "title": "Example",
            "rank": 1,
            "tier": 1,
            "source_tier": "primary",
            "_matched_query_ids": ["q0001"],
        }
        low_info = {
            "text": "Accessibility Statement Skip Navigation Client Login Send a Release Privacy Policy Terms of Use",
            "pages": None,
            "method": "html",
        }
        with mock.patch.object(sac_search, "extract_text_from_url", return_value=low_info):
            rows, failures = sac_search.extract_verified_evidence(
                [source], {"q0001": {"query": "example news"}}, None, "2026-06-06T00:00:00Z", 1, 1
            )

        self.assertEqual(rows, [])
        self.assertEqual(failures[0]["exclude_reason"], "low_information_extract")

    def test_extracted_evidence_carries_source_trust_fields(self):
        source = {
            "source_id": "src_extract",
            "url": "https://example.com/news",
            "title": "Example revenue update",
            "rank": 1,
            "tier": 4,
            "source_tier": "low_confidence",
            "hypothesis_only": True,
            "_matched_query_ids": ["q0001"],
        }
        document = {
            "text": (
                "Example revenue growth accelerated with margin expansion and cash flow improvement "
                "across enterprise customers during the quarter according to management commentary."
            ),
            "pages": None,
            "method": "html",
            "content_type": "text/html",
            "final_url": "https://example.com/news",
            "status_code": 200,
        }
        with mock.patch.object(sac_search, "extract_text_from_url", return_value=document):
            rows, failures = sac_search.extract_verified_evidence(
                [source], {"q0001": {"query": "example revenue growth"}}, "Example", "2026-06-06T00:00:00Z", 1, 1
            )

        self.assertEqual(failures, [])
        self.assertEqual(rows[0]["source_tier"], "low_confidence")
        self.assertTrue(rows[0]["hypothesis_only"])
        self.assertTrue(rows[0]["provenance_verified"])
        self.assertFalse(rows[0]["relevance_verified"])
        self.assertEqual(rows[0]["confidence_basis"], "fetch_plus_keyword_proximity")
        self.assertEqual(rows[0]["final_url"], "https://example.com/news")

    def test_delta_plan_created_for_missing_official_lane(self):
        diagnostics = {
            "issues": [{"code": "no_primary_or_official_sources"}],
            "plan_quality_issues": [{"code": "missing_counterevidence_lane"}],
        }
        plan = {"topic": "Example topic", "mode": "deep", "queries": [{"query": "x", "purpose": "x"}]}
        delta = sac_search.build_delta_plan(plan, diagnostics)
        self.assertIsNotNone(delta)
        assert delta is not None
        purposes = " ".join(query["purpose"].lower() for query in delta["queries"])
        self.assertIn("official", purposes)
        self.assertIn("counterevidence", purposes)
        self.assertEqual(sac_search.validate_plan(delta), [])
        self.assertNotIn("parent_topic", delta)
        self.assertNotIn("generated_at", delta)
        self.assertNotIn("reason_codes", delta)

    def test_schema_allows_issuer_ir_query_type(self):
        schema = json.loads((SCRIPT.parents[1] / "schemas" / "search_plan.schema.json").read_text())
        enum = schema["properties"]["queries"]["items"]["properties"]["query_type"]["enum"]
        self.assertIn("issuer_ir", enum)

    def test_merge_into_project_uses_deep_research_bulk_import_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            dst_dir = root / "project"
            scripts_dir = root / "scripts"
            run_dir.mkdir()
            scripts_dir.mkdir()
            log_path = root / "commands.log"
            (run_dir / "run_manifest.json").write_text(json.dumps({"topic": "bulk import", "mode": "standard"}))
            (run_dir / "sources.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"source_id": "src1", "url": "https://example.com/a", "title": "A", "tier": 2}),
                        json.dumps({"source_id": "src2", "url": "https://example.com/b", "title": "B", "tier": 3}),
                    ]
                )
                + "\n"
            )
            (run_dir / "evidence.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"source_id": "src1", "evidence_quote": "Quote A", "evidence_type": "search_snippet"}),
                        json.dumps({"source_id": "src2", "evidence_quote": "Quote B", "evidence_type": "extracted_quote"}),
                    ]
                )
                + "\n"
            )
            (scripts_dir / "citation_manager.py").write_text(
                """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
log = Path(os.environ["DR_LOG"])
log.write_text(log.read_text() + sys.argv[1] + "\\n" if log.exists() else sys.argv[1] + "\\n")
cmd = sys.argv[1]
if cmd == "init-run":
    out = Path(sys.argv[sys.argv.index("--out-dir") + 1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "sources.jsonl").touch()
    (out / "evidence.jsonl").touch()
    (out / "run_manifest.json").write_text("{}")
    print(json.dumps({"status": "ok"}))
elif cmd == "register-sources":
    jsonl = Path(sys.argv[sys.argv.index("--jsonl") + 1])
    out = Path(sys.argv[sys.argv.index("--dir") + 1])
    rows = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    source_ids = [f"dr{i+1}" for i, _ in enumerate(rows)]
    with (out / "sources.jsonl").open("a") as f:
        for source_id, row in zip(source_ids, rows):
            row["source_id"] = source_id
            f.write(json.dumps(row) + "\\n")
    print(json.dumps({"status": "ok", "registered": len(rows), "duplicates": 0, "errors": [], "source_ids": source_ids}))
elif cmd == "assign-display-numbers":
    print(json.dumps({"status": "ok"}))
else:
    raise SystemExit(f"unexpected citation command: {cmd}")
"""
            )
            (scripts_dir / "evidence_store.py").write_text(
                """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
log = Path(os.environ["DR_LOG"])
log.write_text(log.read_text() + sys.argv[1] + "\\n" if log.exists() else sys.argv[1] + "\\n")
cmd = sys.argv[1]
if cmd == "init":
    out = Path(sys.argv[sys.argv.index("--dir") + 1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.jsonl").touch()
    print(json.dumps({"status": "ok"}))
elif cmd == "add-batch":
    jsonl = Path(sys.argv[sys.argv.index("--jsonl") + 1])
    out = Path(sys.argv[sys.argv.index("--dir") + 1])
    rows = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    with (out / "evidence.jsonl").open("a") as f:
        for row in rows:
            f.write(json.dumps(row) + "\\n")
    print(json.dumps({"status": "ok", "added": len(rows), "duplicates": 0, "errors": [], "evidence_ids": [f"ev{i+1}" for i, _ in enumerate(rows)]}))
else:
    raise SystemExit(f"unexpected evidence command: {cmd}")
"""
            )

            with mock.patch.dict(os.environ, {"DR_LOG": str(log_path)}):
                stats = sac_search.merge_into_project(run_dir, dst_dir, scripts_dir)

            commands = log_path.read_text().splitlines()

        self.assertIn("register-sources", commands)
        self.assertIn("add-batch", commands)
        self.assertNotIn("register-source", commands)
        self.assertNotIn("add", commands)
        self.assertEqual(stats["sources_added"], 2)
        self.assertEqual(stats["evidence_added"], 2)
        self.assertEqual(stats["display_number_status"], "ok")


class SkillRoutingContractTests(unittest.TestCase):
    def test_standard_deep_research_trigger_is_documented(self):
        skill = (SCRIPT.parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Standard, Deep, and UltraDeep", skill)
        self.assertIn("native web search first", skill)
        self.assertIn("second-pass", skill)


if __name__ == "__main__":
    unittest.main()

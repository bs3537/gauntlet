#!/usr/bin/env python3
"""P0 integrity tests for the Hybrid Model Fusion skill."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"


def write_review(path: Path, payload: dict, prelude: str = "") -> None:
    path.write_text(prelude + "```json\n" + json.dumps(payload, indent=2) + "\n```\n", encoding="utf-8")


def score(total: int) -> dict[str, int]:
    each = total // 6
    values = {
        "correctness": each,
        "evidence_quality": each,
        "completeness": each,
        "reasoning_quality": each,
        "calibration": each,
        "actionability": total - each * 5,
    }
    values["total"] = sum(values.values())
    return values


class P0IntegrityTests(unittest.TestCase):
    def test_standard_research_prompts_require_native_then_perplexity(self) -> None:
        runner = (SCRIPTS / "run_hybrid.sh").read_text(encoding="utf-8")
        judge_builder = (SCRIPTS / "build_judge_prompt.py").read_text(encoding="utf-8")
        panel_reference = (SKILL_DIR / "references" / "panel.md").read_text(encoding="utf-8")
        routing_reference = (SKILL_DIR / "references" / "research_routing.md").read_text(encoding="utf-8")

        self.assertIn("research_routing.md", runner)
        for text in (routing_reference, panel_reference):
            self.assertIn("First pass", text)
            self.assertIn("native web search", text)
            self.assertIn("Search-as-Code-style", text)
            self.assertIn("Second pass", text)
            self.assertIn("Perplexity", text)
            self.assertIn("underlying primary", text)

        self.assertIn("WebSearch", judge_builder)
        self.assertIn("Second pass", judge_builder)
        self.assertIn("Perplexity", judge_builder)
        self.assertIn("underlying primary", judge_builder)

    def test_review_packets_include_original_task_and_manifest_order(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hybrid-test-packets-") as tmp:
            run_dir = Path(tmp) / "stable_topic_20260705_120000"
            run_dir.mkdir()
            (run_dir / "original_prompt.md").write_text("Compare the reports against this exact task.", encoding="utf-8")
            for name in ["opus4.8", "grok4.5", "gemini3.5flash", "gpt5.6sol"]:
                (run_dir / f"report_{name}.md").write_text(f"# Report {name}\n\nSubstantial report body.", encoding="utf-8")

            subprocess.run(["python3", str(SCRIPTS / "build_review_packets.py"), str(run_dir)], check=True)

            manifest = json.loads((run_dir / "review_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["original_prompt_file"], "original_prompt.md")
            self.assertNotEqual(manifest["label_assignment_seed"], run_dir.name)
            self.assertEqual(manifest["warnings"], [])
            mapping = json.loads((run_dir / "response_mapping.json").read_text(encoding="utf-8"))
            grok_meta = next(item for item in mapping.values() if item["model"] == "grok4.5")
            self.assertEqual(grok_meta["display"], "Grok 4.5")
            self.assertFalse(grok_meta["fallback_used"])
            for item in manifest["review_prompts"]:
                self.assertEqual(item["reviewed_responses"], item["presentation_order"])
                self.assertEqual(len(item["reviewed_responses"]), 3)
                prompt = (run_dir / item["prompt_file"]).read_text(encoding="utf-8")
                self.assertIn("Compare the reports against this exact task.", prompt)
                self.assertIn("<untrusted_model_report>", prompt)

    def test_aggregate_enforces_manifest_self_filter_and_strong_consensus(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hybrid-test-aggregate-") as tmp:
            run_dir = Path(tmp)
            mapping = {
                "A": {"model": "opus4.8", "display": "Opus 4.8", "file": "report_opus4.8.md"},
                "B": {"model": "grok4.5", "display": "Grok 4.5", "file": "report_grok4.5.md"},
                "C": {"model": "gemini3.5flash", "display": "Gemini 3.5 Flash", "file": "report_gemini3.5flash.md"},
                "D": {"model": "gpt5.6sol", "display": "GPT-5.6 Sol", "file": "report_gpt5.6sol.md"},
            }
            (run_dir / "response_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
            manifest = {
                "review_prompts": [
                    {"reviewer": "opus4.8", "reviewed_responses": ["B", "C", "D"]},
                    {"reviewer": "grok4.5", "reviewed_responses": ["A", "C", "D"]},
                    {"reviewer": "gemini3.5flash", "reviewed_responses": ["A", "B", "D"]},
                    {"reviewer": "gpt5.6sol", "reviewed_responses": ["A", "B", "C"]},
                ]
            }
            (run_dir / "review_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            template_echo = textwrap.dedent(
                """
                ```json
                {
                  "reviewer": "<reviewer-id>",
                  "reviewed_responses": ["<LABEL_1>", "<LABEL_2>"],
                  "ranked_order": ["<LABEL_2>", "<LABEL_1>"],
                  "forced_choice_winner": "<LABEL_2>",
                  "scores": {"<LABEL_1>": {"total": 42}, "<LABEL_2>": {"total": 48}},
                  "confidence": 0.8
                }
                ```
                """
            )
            write_review(
                run_dir / "review_opus4.8.md",
                {
                    "reviewer": "opus4.8",
                    "reviewed_responses": ["A", "B", "C", "D"],
                    "ranked_order": ["A", "B", "C", "D"],
                    "scores": {"A": score(60), "B": score(48), "C": score(36), "D": score(30)},
                    "confidence": 1.0,
                },
                prelude=template_echo,
            )
            write_review(
                run_dir / "review_grok4.5.md",
                {
                    "reviewer": "grok4.5",
                    "reviewed_responses": ["A", "C", "D"],
                    "ranked_order": ["A", "C", "D"],
                    "scores": {"A": score(60), "C": score(30), "D": score(24)},
                    "claim_verdicts": [
                        {
                            "claim": "C used an unsupported figure",
                            "response": "C",
                            "verdict": "weak",
                            "reason": "no source",
                        }
                    ],
                    "confidence": 0.0,
                },
            )
            write_review(
                run_dir / "review_gemini3.5flash.md",
                {
                    "reviewer": "gemini3.5flash",
                    "reviewed_responses": ["A", "B", "D"],
                    "ranked_order": ["A", "B", "D"],
                    "scores": {"A": score(60), "B": score(48), "D": score(30)},
                    "confidence": 1.0,
                },
            )
            write_review(
                run_dir / "review_gpt5.6sol.md",
                {
                    "reviewer": "gpt5.6sol",
                    "reviewed_responses": ["A", "B", "C"],
                    "ranked_order": ["A", "B", "C"],
                    "scores": {"A": score(60), "B": score(48), "C": score(36)},
                    "confidence": 1.0,
                },
            )

            subprocess.run(["python3", str(SCRIPTS / "aggregate_reviews.py"), str(run_dir)], check=True)
            scorecard = json.loads((run_dir / "aggregate_scorecard.json").read_text(encoding="utf-8"))
            normalized_opus = json.loads((run_dir / "review_opus4.8.json").read_text(encoding="utf-8"))
            normalized_gpt = json.loads((run_dir / "review_grok4.5.json").read_text(encoding="utf-8"))

            self.assertNotIn("A", normalized_opus["ranked_order"])
            self.assertNotIn("A", normalized_opus["scores"])
            self.assertEqual(normalized_gpt["confidence"], 0.0)
            self.assertEqual(scorecard["consensus_label"], "strong_consensus")
            top = scorecard["responses"][0]
            self.assertEqual(top["response"], "A")
            self.assertEqual(top["borda_rate"], 1.0)
            self.assertTrue((run_dir / "contested_claims.json").is_file())
            self.assertTrue((run_dir / "contested_claims.md").is_file())
            self.assertTrue(any("stripped self-ballot" in warning for warning in scorecard["warnings"]))
            self.assertTrue(any("confidence is 0.0" in warning for warning in scorecard["warnings"]))

    def test_runner_scripts_pin_codex_and_file_handoff_large_agy_prompts(self) -> None:
        run_codex = (SCRIPTS / "run_codex.sh").read_text(encoding="utf-8")
        self.assertIn('FUSION_CODEX_MODEL:-gpt-5.6-sol', run_codex)
        self.assertIn('effort="${3:-max}"', run_codex)
        self.assertIn('-m "$attempt_model"', run_codex)
        self.assertIn("--json", run_codex)

        with tempfile.TemporaryDirectory(prefix="hybrid-test-agy-") as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            codex_args_file = tmp_path / "codex_args.txt"
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" >> \"$CODEX_ARGS_FILE\"\n"
                "args=\"$*\"\n"
                "out=''\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  [ \"$1\" = '-o' ] && { out=\"$2\"; shift 2; continue; }\n"
                "  shift\n"
                "done\n"
                "cat >/dev/null\n"
                "if [[ \"$args\" == *\"-m gpt-5.6-sol\"* ]]; then\n"
                "  if [ \"${CODEX_FAKE_MODE:-success}\" = 'safety' ] || [ \"${CODEX_FAKE_MODE:-success}\" = 'fallback_error' ]; then\n"
                "    printf '%s\\n' '{\"type\":\"error\",\"error\":{\"code\":\"content_policy_violation\",\"message\":\"blocked\"}}'\n"
                "    exit 17\n"
                "  fi\n"
                "  if [ \"${CODEX_FAKE_MODE:-success}\" = 'generic_error' ]; then\n"
                "    printf '%s\\n' '{\"type\":\"error\",\"error\":{\"code\":\"model_not_found\",\"message\":\"not found\"}}'\n"
                "    exit 17\n"
                "  fi\n"
                "  if [ \"${CODEX_FAKE_MODE:-success}\" = 'nested_conflict' ]; then\n"
                "    printf '%s\\n' '{\"type\":\"error\",\"error\":{\"code\":\"model_not_found\",\"metadata\":{\"type\":\"safety_violation\"}}}'\n"
                "    exit 17\n"
                "  fi\n"
                "fi\n"
                "if [[ \"$args\" == *\"-m gpt-5.5\"* ]] && [ \"${CODEX_FAKE_MODE:-success}\" = 'fallback_error' ]; then\n"
                "  printf '%s\\n' '{\"type\":\"error\",\"error\":{\"code\":\"service_unavailable\",\"message\":\"unavailable\"}}'\n"
                "  exit 18\n"
                "fi\n"
                "printf 'fake codex output with enough content to be non-empty\\n' > \"$out\"\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            codex_prompt = tmp_path / "prompt_grok4.5.txt"
            codex_prompt.write_text("Verify the configured Codex runner arguments.", encoding="utf-8")
            codex_output = tmp_path / "report_grok4.5.md"
            codex_env = os.environ.copy()
            codex_env.update(
                {
                    "PATH": f"{fake_bin}:{codex_env['PATH']}",
                    "CODEX_ARGS_FILE": str(codex_args_file),
                    "FUSION_TIMEOUT": "5",
                }
            )
            subprocess.run(
                [str(SCRIPTS / "run_codex.sh"), str(codex_prompt), str(codex_output)],
                check=True,
                env=codex_env,
            )
            codex_args = codex_args_file.read_text(encoding="utf-8")
            self.assertIn("gpt-5.6-sol", codex_args)
            self.assertIn("model_reasoning_effort=max", codex_args)

            codex_args_file.write_text("", encoding="utf-8")
            codex_env["CODEX_FAKE_MODE"] = "safety"
            subprocess.run(
                [str(SCRIPTS / "run_codex.sh"), str(codex_prompt), str(codex_output)],
                check=True,
                env=codex_env,
            )
            safety_args = codex_args_file.read_text(encoding="utf-8")
            self.assertIn("gpt-5.6-sol", safety_args)
            self.assertIn("model_reasoning_effort=max", safety_args)
            self.assertIn("gpt-5.5", safety_args)
            self.assertIn("model_reasoning_effort=xhigh", safety_args)
            routing = json.loads(
                codex_output.with_suffix(codex_output.suffix + ".routing.json").read_text(encoding="utf-8")
            )
            self.assertTrue(routing["fallback_used"])
            self.assertEqual(routing["resolved_model"], "gpt-5.5")
            self.assertEqual(routing["resolved_effort"], "xhigh")
            self.assertEqual(len(routing["prompt_sha256"]), 64)

            codex_args_file.write_text("", encoding="utf-8")
            codex_env.update(
                {
                    "CODEX_FAKE_MODE": "safety",
                    "FUSION_RUN_STAGE": "review",
                    "FUSION_REVIEW_LEAST_PRIVILEGE": "1",
                }
            )
            review_output = tmp_path / "review_grok4.5.md"
            subprocess.run(
                [str(SCRIPTS / "run_codex.sh"), str(codex_prompt), str(review_output)],
                check=True,
                env=codex_env,
            )
            review_args = codex_args_file.read_text(encoding="utf-8")
            self.assertEqual(review_args.count("--output-schema"), 2)
            self.assertGreaterEqual(review_args.count("read-only"), 2)
            self.assertIn("gpt-5.6-sol", review_args)
            self.assertIn("gpt-5.5", review_args)
            self.assertIn("model_reasoning_effort=max", review_args)
            self.assertIn("model_reasoning_effort=xhigh", review_args)
            review_routing = json.loads(
                review_output.with_suffix(review_output.suffix + ".routing.json").read_text(encoding="utf-8")
            )
            self.assertEqual(review_routing["stage"], "review")

            codex_args_file.write_text("", encoding="utf-8")
            codex_env.update({"CODEX_FAKE_MODE": "generic_error", "FUSION_RUN_STAGE": "panel"})
            codex_env.pop("FUSION_REVIEW_LEAST_PRIVILEGE")
            failed = subprocess.run(
                [str(SCRIPTS / "run_codex.sh"), str(codex_prompt), str(codex_output)],
                check=False,
                env=codex_env,
            )
            self.assertNotEqual(failed.returncode, 0)
            generic_args = codex_args_file.read_text(encoding="utf-8")
            self.assertIn("gpt-5.6-sol", generic_args)
            self.assertNotIn("gpt-5.5", generic_args)

            codex_args_file.write_text("", encoding="utf-8")
            codex_env["CODEX_FAKE_MODE"] = "nested_conflict"
            nested = subprocess.run(
                [str(SCRIPTS / "run_codex.sh"), str(codex_prompt), str(codex_output)],
                check=False,
                env=codex_env,
            )
            self.assertNotEqual(nested.returncode, 0)
            nested_args = codex_args_file.read_text(encoding="utf-8")
            self.assertIn("gpt-5.6-sol", nested_args)
            self.assertNotIn("gpt-5.5", nested_args)

            # Grok 4.5 panelist dispatch: fusion_reliability routes grok4.5 -> run_grok.sh,
            # which invokes the Grok Build CLI with -m grok-4.5 and the requested effort.
            codex_env.pop("CODEX_FAKE_MODE", None)
            grok_args_file = tmp_path / "grok_args.txt"
            fake_grok = fake_bin / "grok"
            fake_grok.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" > \"$GROK_ARGS_FILE\"\n"
                "printf 'fake grok panelist output with enough content to be non-empty\\n'\n",
                encoding="utf-8",
            )
            fake_grok.chmod(0o755)
            grok_prompt = tmp_path / "prompt_grok_dispatch.txt"
            grok_prompt.write_text("Verify the configured Grok runner arguments.", encoding="utf-8")
            grok_output = tmp_path / "report_grok_dispatch.md"
            grok_env = os.environ.copy()
            grok_env.update(
                {
                    "PATH": f"{fake_bin}:{grok_env['PATH']}",
                    "GROK_ARGS_FILE": str(grok_args_file),
                    "FUSION_GROK_BIN": str(fake_grok),
                    "FUSION_TIMEOUT": "5",
                }
            )
            dispatch = subprocess.run(
                [
                    "bash",
                    "-c",
                    '. "$1"; _fusion_run_one grok4.5 "$2" "$3" high 0 panel',
                    "hybrid-grok-test",
                    str(SCRIPTS / "fusion_reliability.sh"),
                    str(grok_prompt),
                    str(grok_output),
                ],
                check=False,
                env=grok_env,
            )
            self.assertEqual(dispatch.returncode, 0)
            self.assertTrue(grok_output.is_file() and grok_output.stat().st_size > 0)
            grok_args = grok_args_file.read_text(encoding="utf-8").splitlines()
            self.assertIn("grok-4.5", grok_args)
            self.assertIn("high", grok_args)
            self.assertIn("--prompt-file", grok_args)

            args_file = tmp_path / "agy_args.txt"
            fake_agy = fake_bin / "agy"
            fake_agy.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" > \"$AGY_ARGS_FILE\"\n"
                "printf 'fake gemini output with enough content to be non-empty\\n'\n",
                encoding="utf-8",
            )
            fake_agy.chmod(0o755)
            prompt = tmp_path / "review_prompt_gemini3.5flash.txt"
            prompt.write_text("X" * 256, encoding="utf-8")
            output = tmp_path / "review_gemini3.5flash.md"
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "AGY_ARGS_FILE": str(args_file),
                    "FUSION_TIMEOUT": "5",
                    "FUSION_AGY_ARG_MAX_BYTES": "100",
                }
            )

            subprocess.run([str(SCRIPTS / "run_gemini.sh"), str(prompt), str(output)], check=True, env=env)
            args = args_file.read_text(encoding="utf-8")
            self.assertIn("--add-dir", args)
            self.assertIn(str(tmp_path), args)
            self.assertIn("Read the full prompt", args)
            self.assertNotIn("X" * 128, args)

    def test_judge_prompt_is_blind_by_default_and_parameterized(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hybrid-test-judge-") as tmp:
            run_dir = Path(tmp)
            (run_dir / "original_prompt.md").write_text("Original task text", encoding="utf-8")
            mapping = {
                "A": {"model": "opus4.8", "display": "Opus 4.8", "file": "report_opus4.8.md"},
                "B": {"model": "grok4.5", "display": "Grok 4.5", "file": "report_grok4.5.md"},
            }
            (run_dir / "response_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
            (run_dir / "report_opus4.8.md").write_text("Panel report one", encoding="utf-8")
            (run_dir / "report_grok4.5.md").write_text("Panel report two", encoding="utf-8")
            (run_dir / "review_opus4.8.md").write_text("Review one", encoding="utf-8")
            (run_dir / "aggregate_scorecard.md").write_text("Scorecard with Opus 4.8 identity", encoding="utf-8")
            (run_dir / "aggregate_scorecard.json").write_text(
                json.dumps(
                    {
                        "consensus_label": "weak_consensus",
                        "valid_review_count": 1,
                        "expected_review_count": 2,
                        "responses": [
                            {
                                "aggregate_rank": 1,
                                "response": "A",
                                "borda_points": 1,
                                "borda_rate": 1,
                                "avg_total_score": 50,
                                "weighted_total_score": 50,
                                "reviews_received": 1,
                                "score_stdev": 0,
                            }
                        ],
                        "peer_rankings": [{"reviewer": "opus4.8", "ranked_order": ["A", "B"]}],
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["FUSION_JUDGE_MODEL"] = "claude-fable-5"
            subprocess.run(["python3", str(SCRIPTS / "build_judge_prompt.py"), str(run_dir)], check=True, env=env)
            prompt = (run_dir / "judge_prompt.txt").read_text(encoding="utf-8")
            self.assertIn("You are claude-fable-5 at max effort", prompt)
            self.assertIn("Judge blinding is ON", prompt)
            self.assertNotIn("## Response Mapping", prompt)
            self.assertNotIn("Scorecard with Opus 4.8 identity", prompt)
            self.assertIn("### Response A", prompt)
            self.assertIn("<untrusted_model_report>", prompt)
            self.assertIn("two-pass adjudication structure", prompt)

            env["FUSION_JUDGE_BLIND"] = "0"
            subprocess.run(["python3", str(SCRIPTS / "build_judge_prompt.py"), str(run_dir)], check=True, env=env)
            unblind_prompt = (run_dir / "judge_prompt.txt").read_text(encoding="utf-8")
            self.assertIn("## Response Mapping", unblind_prompt)
            self.assertIn("Opus 4.8", unblind_prompt)

    def test_eval_harness_dry_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hybrid-test-eval-") as tmp:
            subprocess.run(
                ["bash", str(SKILL_DIR / "eval" / "run_eval.sh"), "--dry-run", "--out", tmp],
                check=True,
            )
            results = json.loads((Path(tmp) / "eval_results.json").read_text(encoding="utf-8"))
            self.assertIn("arms", results)
            self.assertTrue(any(row["arm"] == "hybrid" for row in results["arms"]))
            self.assertEqual(results["warnings"], [])
            self.assertTrue((Path(tmp) / "eval_results.md").is_file())

    def test_review_json_validator_and_render_targets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hybrid-test-review-validator-") as tmp:
            run_dir = Path(tmp)
            mapping = {
                "A": {"model": "opus4.8", "display": "Opus 4.8", "file": "report_opus4.8.md"},
                "B": {"model": "grok4.5", "display": "Grok 4.5", "file": "report_grok4.5.md"},
                "C": {"model": "gemini3.5flash", "display": "Gemini 3.5 Flash", "file": "report_gemini3.5flash.md"},
            }
            (run_dir / "response_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
            (run_dir / "review_manifest.json").write_text(
                json.dumps({"review_prompts": [{"reviewer": "opus4.8", "reviewed_responses": ["B", "C"]}]}),
                encoding="utf-8",
            )
            write_review(
                run_dir / "review_opus4.8.md",
                {
                    "reviewer": "opus4.8",
                    "reviewed_responses": ["B", "C"],
                    "ranked_order": ["B", "C"],
                    "scores": {"B": score(48), "C": score(36)},
                    "confidence": 0.9,
                },
            )
            subprocess.run(
                [
                    "python3",
                    str(SCRIPTS / "validate_review_json.py"),
                    str(run_dir),
                    "opus4.8",
                    str(run_dir / "review_opus4.8.md"),
                ],
                check=True,
            )
            (run_dir / "report_fusion.md").write_text("# Fusion\n\nbody", encoding="utf-8")
            subprocess.run(["bash", str(SCRIPTS / "render_html.sh"), str(run_dir), "Smoke"], check=True)
            self.assertTrue((run_dir / "report_fusion.html").is_file())

    def test_detect_panel_can_write_run_env(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hybrid-test-env-") as tmp:
            # This test only checks run_env.json writing; skip the auth-preflight gate so it does not
            # depend on live, authenticated CLIs (the gate itself is covered by test_hardening.sh).
            env = {**os.environ, "FUSION_AUTH_PREFLIGHT": "0"}
            subprocess.run(["bash", str(SCRIPTS / "detect_panel.sh"), tmp], check=True, env=env)
            env_json = json.loads((Path(tmp) / "run_env.json").read_text(encoding="utf-8"))
            self.assertIn("commands", env_json)
            self.assertIn("auth_checks", env_json)
            self.assertEqual(env_json["judge_model"], os.environ.get("FUSION_JUDGE_MODEL", "claude-opus-4-8"))
            self.assertEqual(env_json["grok_model"], os.environ.get("FUSION_GROK_MODEL", "grok-4.5"))
            self.assertEqual(env_json["grok_effort"], os.environ.get("FUSION_GROK_EFFORT", "high"))

    def test_report_recommendation_matrix_is_wired(self) -> None:
        tasks = [
            json.loads(line)
            for line in (SKILL_DIR / "eval" / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertGreaterEqual(len(tasks), 15)
        self.assertGreaterEqual(sum(1 for task in tasks if str(task["id"]).startswith("needle_")), 2)

        panel_config = json.loads((SKILL_DIR / "config" / "panel.json").read_text(encoding="utf-8"))
        for preset in ["default", "fable-panelist", "deweighted-gemini", "budget"]:
            self.assertIn(preset, panel_config["presets"])

        schema = json.loads((SKILL_DIR / "config" / "review_output_schema.json").read_text(encoding="utf-8"))
        self.assertIn("ranked_order", schema["required"])

        run_claude = (SCRIPTS / "run_claude.sh").read_text(encoding="utf-8")
        self.assertIn("--setting-sources", run_claude)
        self.assertIn("FUSION_CLAUDE_PANEL_SETTING_SOURCES:-project", run_claude)

        run_codex = (SCRIPTS / "run_codex.sh").read_text(encoding="utf-8")
        self.assertIn("--output-schema", run_codex)

        panel_json = subprocess.run(
            ["python3", str(SCRIPTS / "panel_config.py"), "panel-json"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
        self.assertIn("opus4.8", panel_json)

        env = os.environ.copy()
        env["FUSION_PANEL_PRESET"] = "fable-panelist"
        models = subprocess.run(
            ["python3", str(SCRIPTS / "panel_config.py"), "models"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            env=env,
        ).stdout.splitlines()
        self.assertEqual(models, ["fable5", "grok4.5", "gemini3.5flash"])


class HardeningSuiteTest(unittest.TestCase):
    def test_hardening_bash_suite(self):
        """Offline hardening suite: transient retry, agy stub recovery, auth preflight, run_hybrid abort."""
        result = subprocess.run(
            ["bash", str(SCRIPTS / "test_hardening.sh")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("[test_hardening] passed", result.stdout)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Interactive advancement rules testing script.

Features:
- Multi-config file support for different scenarios
- Full CRUD operations on rules
- Test rules against real candidates
- Monitoring and statistics
- Dry-run comparison reports

Usage:
    python scripts/test_advancement_rules.py
    python scripts/test_advancement_rules.py --url https://staging.onrender.com
    python scripts/test_advancement_rules.py --config configs/tech_screen.json

Environment Variables:
    TEST_BASE_URL: Default base URL for API calls (default: http://localhost:8000)
    DATABASE_URL: PostgreSQL connection string (for direct DB queries)

Examples:
    # Interactive menu (localhost)
    python scripts/test_advancement_rules.py

    # Use staging environment
    python scripts/test_advancement_rules.py --url https://staging.onrender.com

    # Load specific config
    python scripts/test_advancement_rules.py --config scripts/configs/tech_screen.json
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg
import httpx

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configuration
DEFAULT_BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
CONFIGS_DIR = Path(__file__).parent / "configs"


# ============================================================================
# Helper Classes
# ============================================================================


class ConfigManager:
    """Manages config file loading, saving, and validation."""

    @staticmethod
    def list_available_configs() -> list[Path]:
        """Scan configs directory for JSON files."""
        if not CONFIGS_DIR.exists():
            return []
        return sorted(CONFIGS_DIR.glob("*.json"))

    @staticmethod
    def load_config(filepath: Path) -> dict[str, Any]:
        """Load and validate JSON config file."""
        with open(filepath) as f:
            config = json.load(f)

        # Basic validation
        required_fields = [
            "name",
            "interview_plan_id",
            "interview_stage_id",
            "interviews",
        ]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Config missing required field: {field}")

        return config

    @staticmethod
    def save_config(config: dict[str, Any], filepath: Path) -> None:
        """Save config to JSON file."""
        with open(filepath, "w") as f:
            json.dump(config, f, indent=2)


class RuleAPIClient:
    """Wraps all HTTP calls to admin API endpoints."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url
        self.timeout = timeout

    async def health_check(self) -> dict[str, Any]:
        """Check application health."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()

    async def create_rule(self, rule_data: dict[str, Any]) -> dict[str, Any]:
        """Create advancement rule."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/admin/create-advancement-rule", json=rule_data
            )
            response.raise_for_status()
            return response.json()

    async def list_rules(self, active_only: bool = True) -> dict[str, Any]:
        """List all advancement rules."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/admin/rules", params={"active_only": active_only}
            )
            response.raise_for_status()
            return response.json()

    async def get_rule(self, rule_id: str) -> dict[str, Any]:
        """Get specific rule details."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/admin/rules/{rule_id}")
            response.raise_for_status()
            return response.json()

    async def delete_rule(self, rule_id: str) -> dict[str, Any]:
        """Delete (soft-delete) a rule."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.delete(f"{self.base_url}/admin/rules/{rule_id}")
            response.raise_for_status()
            return response.json()

    async def trigger_evaluation(
        self, schedule_id: str | None = None, application_id: str | None = None
    ) -> dict[str, Any]:
        """Manually trigger advancement evaluation."""
        params = {}
        if schedule_id:
            params["schedule_id"] = schedule_id
        elif application_id:
            params["application_id"] = application_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/admin/trigger-advancement-evaluation", params=params
            )
            response.raise_for_status()
            return response.json()

    async def get_stats(self) -> dict[str, Any]:
        """Get advancement statistics."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/admin/stats")
            response.raise_for_status()
            return response.json()


class TableFormatter:
    """Formats data as nice CLI tables."""

    @staticmethod
    def print_header(text: str, width: int = 70) -> None:
        """Print section header."""
        print(f"\n{'=' * width}")
        print(f"  {text}")
        print(f"{'=' * width}\n")

    @staticmethod
    def print_success(text: str) -> None:
        """Print success message."""
        print(f"✓ {text}")

    @staticmethod
    def print_error(text: str) -> None:
        """Print error message."""
        print(f"✗ {text}")

    @staticmethod
    def print_warning(text: str) -> None:
        """Print warning message."""
        print(f"⚠ {text}")

    @staticmethod
    def print_info(text: str) -> None:
        """Print info message."""
        print(f"ℹ {text}")

    @staticmethod
    def print_table(
        headers: list[str], rows: list[list[str]], widths: list[int] | None = None
    ) -> None:
        """Print formatted table."""
        if not rows:
            print("  (No data)")
            return

        # Auto-calculate widths if not provided
        if widths is None:
            widths = [len(h) for h in headers]
            for row in rows:
                for i, cell in enumerate(row):
                    if i < len(widths):
                        widths[i] = max(widths[i], len(str(cell)))

        # Print header
        header_row = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
        print(f"  {header_row}")
        print(f"  {'-' * (sum(widths) + 2 * (len(headers) - 1))}")

        # Print rows
        for row in rows:
            row_str = "  ".join(str(cell).ljust(w) for cell, w in zip(row, widths, strict=False))
            print(f"  {row_str}")

    @staticmethod
    def truncate(text: str, max_len: int = 40) -> str:
        """Truncate text with ellipsis."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."


# ============================================================================
# Database Query Helper
# ============================================================================


async def query_database(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Direct database query for advanced monitoring (read-only)."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]
    finally:
        await conn.close()


# ============================================================================
# Configuration Management Functions
# ============================================================================


def select_config() -> dict[str, Any] | None:
    """Interactive config selection."""
    fmt = TableFormatter()
    fmt.print_header("Select Configuration File")

    configs = ConfigManager.list_available_configs()

    if not configs:
        fmt.print_warning(f"No config files found in {CONFIGS_DIR}")
        fmt.print_info("Create a config file using the examples in scripts/configs/")
        return None

    print("Available configurations:")
    for i, config_path in enumerate(configs, 1):
        print(f"  {i}. {config_path.name}")

    print(f"  {len(configs) + 1}. Enter custom path")
    print("  0. Cancel")

    try:
        choice = int(input("\nSelect config: ").strip())

        if choice == 0:
            return None
        elif 1 <= choice <= len(configs):
            config_path = configs[choice - 1]
        elif choice == len(configs) + 1:
            path_str = input("Enter config file path: ").strip()
            config_path = Path(path_str)
        else:
            fmt.print_error("Invalid choice")
            return None

        config = ConfigManager.load_config(config_path)
        fmt.print_success(f"Loaded config: {config['name']}")
        return config

    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        fmt.print_error(f"Error loading config: {e}")
        return None


def view_config(config: dict[str, Any] | None) -> None:
    """Display current config details."""
    fmt = TableFormatter()
    fmt.print_header("Current Configuration")

    if not config:
        fmt.print_warning("No config loaded")
        return

    print(f"  Name: {config.get('name', 'N/A')}")
    print(f"  Description: {config.get('description', 'N/A')}")
    print(f"  Job ID: {config.get('job_id', 'null (global)')}")
    print(f"  Interview Plan ID: {config.get('interview_plan_id', 'N/A')}")
    print(f"  Interview Stage ID: {config.get('interview_stage_id', 'N/A')}")
    print(f"  Target Stage ID: {config.get('target_stage_id', 'null (sequential)')}")
    print(f"  Default Operator: {config.get('default_operator', '>=')} ")
    print(f"  Default Threshold: {config.get('default_threshold', '3')}")

    print("\n  Interviews:")
    for i, interview in enumerate(config.get("interviews", []), 1):
        print(f"\n    {i}. {interview.get('name', 'N/A')}")
        print(f"       ID: {interview.get('interview_id', 'N/A')}")
        print(f"       Score Fields: {', '.join(interview.get('score_fields', []))}")


def edit_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Interactive config editing."""
    fmt = TableFormatter()
    fmt.print_header("Edit Configuration")

    if not config:
        fmt.print_warning("No config loaded")
        return None

    print("Which field do you want to edit?")
    print("  1. Interview Plan ID")
    print("  2. Interview Stage ID")
    print("  3. Target Stage ID")
    print("  4. Job ID")
    print("  5. Interview IDs")
    print("  0. Cancel")

    try:
        choice = int(input("\nSelect field: ").strip())

        if choice == 0:
            return config
        elif choice == 1:
            config["interview_plan_id"] = input("Enter Interview Plan ID: ").strip()
        elif choice == 2:
            config["interview_stage_id"] = input("Enter Interview Stage ID: ").strip()
        elif choice == 3:
            value = input("Enter Target Stage ID (or 'null' for sequential): ").strip()
            config["target_stage_id"] = None if value.lower() == "null" else value
        elif choice == 4:
            value = input("Enter Job ID (or 'null' for global): ").strip()
            config["job_id"] = None if value.lower() == "null" else value
        elif choice == 5:
            for i, interview in enumerate(config.get("interviews", []), 1):
                print(f"\n{i}. {interview.get('name')}")
                new_id = input("   Enter new ID (or press Enter to skip): ").strip()
                if new_id:
                    interview["interview_id"] = new_id
        else:
            fmt.print_error("Invalid choice")
            return config

        fmt.print_success("Config updated")

        # Ask to save
        save = input("\nSave changes to file? (y/n): ").strip().lower()
        if save == "y":
            filename = input("Enter filename (in scripts/configs/): ").strip()
            filepath = CONFIGS_DIR / filename
            ConfigManager.save_config(config, filepath)
            fmt.print_success(f"Saved to {filepath}")

        return config

    except (ValueError, KeyError) as e:
        fmt.print_error(f"Error editing config: {e}")
        return config


# ============================================================================
# Rule Management Functions
# ============================================================================


async def create_rule_wizard(client: RuleAPIClient, config: dict[str, Any] | None) -> None:
    """Step-by-step rule creation wizard."""
    fmt = TableFormatter()
    fmt.print_header("Create Advancement Rule - Wizard")

    if not config:
        fmt.print_warning("No config loaded. Load a config first.")
        return

    try:
        # Step 1: Rule scope
        print("Step 1: Rule Scope")
        print("  1. Global rule (applies to all jobs using this plan/stage)")
        print("  2. Job-specific rule")
        scope = input("Select: ").strip()

        job_id = config.get("job_id")
        if scope == "2":
            job_id = input("Enter Job ID: ").strip() or None

        # Step 2: Target stage
        print("\nStep 2: Target Stage")
        print("  1. Next sequential stage (automatic)")
        print("  2. Specific stage (skip stages)")
        target_choice = input("Select: ").strip()

        target_stage_id = config.get("target_stage_id")
        if target_choice == "2":
            target_stage_id = input("Enter Target Stage ID: ").strip() or None

        # Step 3: Requirements
        print("\nStep 3: Requirements")
        print("Select interviews and score thresholds:\n")

        requirements = []
        interviews = config.get("interviews", [])

        for i, interview in enumerate(interviews, 1):
            print(f"{i}. {interview['name']}")
            include = input("   Include this interview? (y/n): ").strip().lower()

            if include == "y":
                print(f"   Available score fields: {', '.join(interview['score_fields'])}")
                score_field = input("   Score field to check: ").strip()

                operator = input(
                    "   Operator (default: {}): ".format(config.get("default_operator", ">="))
                ).strip() or config.get("default_operator", ">=")

                threshold = input(
                    "   Threshold value (default: {}): ".format(
                        config.get("default_threshold", "3")
                    )
                ).strip() or config.get("default_threshold", "3")

                requirements.append(
                    {
                        "interview_id": interview["interview_id"],
                        "score_field_path": score_field,
                        "operator": operator,
                        "threshold_value": threshold,
                        "is_required": True,
                    }
                )

        if not requirements:
            fmt.print_error("No requirements added. Cancelling.")
            return

        # Step 4: Actions (default to advance_stage)
        actions = [{"action_type": "advance_stage", "execution_order": 1}]

        # Step 5: Preview
        fmt.print_header("Preview Rule")
        rule_data = {
            "job_id": job_id,
            "interview_plan_id": config["interview_plan_id"],
            "interview_stage_id": config["interview_stage_id"],
            "target_stage_id": target_stage_id,
            "requirements": requirements,
            "actions": actions,
        }

        print(json.dumps(rule_data, indent=2))

        # Confirm
        confirm = input("\nCreate this rule? (y/n): ").strip().lower()
        if confirm != "y":
            fmt.print_warning("Cancelled")
            return

        # Create rule
        print("\nCreating rule...")
        result = await client.create_rule(rule_data)

        fmt.print_success("Rule created successfully!")
        print(f"  Rule ID: {result['rule_id']}")
        print(f"  Requirements: {len(result['requirement_ids'])} created")
        print(f"  Actions: {len(result['action_ids'])} created")

    except Exception as e:
        fmt.print_error(f"Error creating rule: {e}")


async def list_rules_display(client: RuleAPIClient) -> None:
    """Display all active rules in formatted table."""
    fmt = TableFormatter()
    fmt.print_header("Active Advancement Rules")

    try:
        data = await client.list_rules(active_only=True)
        rules = data.get("rules", [])

        if not rules:
            fmt.print_info("No active rules found")
            return

        print(f"Total active rules: {len(rules)}\n")

        for rule in rules:
            rule_id = rule["rule_id"][:8] + "..."
            scope = "Global" if not rule["job_id"] else f"Job: {rule['job_id'][:8]}..."
            req_count = len(rule.get("requirements", []))
            created = rule.get("created_at", "N/A")[:10] if rule.get("created_at") else "N/A"

            print(f"  {rule_id}")
            print(f"    Scope: {scope}")
            print(f"    Stage: {rule['interview_stage_id'][:8]}...")
            print(f"    Requirements: {req_count}")
            print(f"    Created: {created}")
            print()

        # Option to view details
        view = input("View details of a rule? Enter rule_id (or press Enter to skip): ").strip()
        if view:
            await view_rule_details(client, view)

    except Exception as e:
        fmt.print_error(f"Error listing rules: {e}")


async def view_rule_details(client: RuleAPIClient, rule_id: str | None = None) -> None:
    """Display detailed information about a specific rule."""
    fmt = TableFormatter()
    fmt.print_header("Rule Details")

    try:
        if not rule_id:
            rule_id = input("Enter Rule ID: ").strip()

        rule = await client.get_rule(rule_id)

        print(f"Rule ID: {rule['rule_id']}")
        print(f"Job ID: {rule['job_id'] or '(global)'}")
        print(f"Interview Plan ID: {rule['interview_plan_id']}")
        print(f"Interview Stage ID: {rule['interview_stage_id']}")
        print(f"Target Stage ID: {rule['target_stage_id'] or '(sequential)'}")
        print(f"Active: {rule['is_active']}")
        print(f"Created: {rule.get('created_at', 'N/A')}")

        print("\nRequirements:")
        for i, req in enumerate(rule.get("requirements", []), 1):
            print(f"  {i}. Interview: {req['interview_id'][:8]}...")
            print(f"     Field: {req['score_field_path']}")
            print(f"     Condition: {req['operator']} {req['threshold_value']}")
            print(f"     Required: {req['is_required']}")

        print("\nActions:")
        for i, action in enumerate(rule.get("actions", []), 1):
            print(f"  {i}. Type: {action['action_type']}")
            print(f"     Order: {action['execution_order']}")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            fmt.print_error("Rule not found")
        else:
            fmt.print_error(f"Error: {e}")
    except Exception as e:
        fmt.print_error(f"Error viewing rule: {e}")


async def delete_rule_interactive(client: RuleAPIClient) -> None:
    """Interactively delete a rule."""
    fmt = TableFormatter()
    fmt.print_header("Delete Rule")

    try:
        rule_id = input("Enter Rule ID to delete: ").strip()

        # Show rule details first
        await view_rule_details(client, rule_id)

        # Confirm deletion
        confirm = input("\nAre you sure you want to delete this rule? (yes/no): ").strip().lower()

        if confirm != "yes":
            fmt.print_warning("Cancelled")
            return

        result = await client.delete_rule(rule_id)
        fmt.print_success(f"Rule deleted: {result['rule_id']}")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            fmt.print_error("Rule not found or already deleted")
        else:
            fmt.print_error(f"Error: {e}")
    except Exception as e:
        fmt.print_error(f"Error deleting rule: {e}")


# ============================================================================
# Testing & Evaluation Functions
# ============================================================================


async def test_against_candidate(client: RuleAPIClient) -> None:
    """Test rule evaluation against a specific candidate."""
    fmt = TableFormatter()
    fmt.print_header("Test Rule Against Candidate")

    try:
        print("Enter either schedule_id or application_id:")
        candidate_id = input("ID: ").strip()

        # Try to determine if it's a schedule or application
        id_type = input("Is this a schedule_id or application_id? (s/a): ").strip().lower()

        print("\nTriggering evaluation...")

        if id_type == "s":
            result = await client.trigger_evaluation(schedule_id=candidate_id)
        else:
            result = await client.trigger_evaluation(application_id=candidate_id)

        # Display results
        if "evaluation" in result:
            eval_data = result["evaluation"]
            ready = eval_data.get("ready", False)

            if ready:
                fmt.print_success("Candidate is READY for advancement!")
                print(f"  Rule ID: {eval_data.get('rule_id', 'N/A')}")
                print(f"  Target Stage: {eval_data.get('target_stage_id', 'N/A')}")
            else:
                fmt.print_warning("Candidate is NOT ready for advancement")
                print(f"  Blocking Reason: {eval_data.get('blocking_reason', 'N/A')}")

            # Show evaluation results detail
            eval_results = eval_data.get("evaluation_results")
            if eval_results:
                print("\nEvaluation Details:")
                print(json.dumps(eval_results, indent=2))

        elif "results" in result:
            # Multiple schedules (from application_id)
            fmt.print_info(f"Evaluated {result['schedules_evaluated']} schedule(s)")
            for sched_result in result["results"]:
                print(f"\n  Schedule: {sched_result['schedule_id'][:8]}...")
                eval_data = sched_result["evaluation"]
                ready = eval_data.get("ready", False)
                status = "READY" if ready else "BLOCKED"
                print(f"  Status: {status}")
                if not ready:
                    print(f"  Reason: {eval_data.get('blocking_reason', 'N/A')}")

    except Exception as e:
        fmt.print_error(f"Error testing candidate: {e}")


async def batch_test_rules(client: RuleAPIClient) -> None:
    """Find recent completed schedules and test all rules."""
    fmt = TableFormatter()
    fmt.print_header("Batch Test Rules")

    try:
        limit = input("Number of recent schedules to test (default: 10): ").strip() or "10"
        limit = int(limit)

        fmt.print_info("Querying database for recent completed schedules...")

        # Query database for recent schedules
        query = """
            SELECT schedule_id, application_id, status, updated_at
            FROM interview_schedules
            WHERE status = 'Complete'
            ORDER BY updated_at DESC
            LIMIT $1
        """

        schedules = await query_database(query, (limit,))

        if not schedules:
            fmt.print_warning("No completed schedules found")
            return

        fmt.print_info(f"Found {len(schedules)} completed schedule(s). Testing...")

        tested = 0
        ready_count = 0

        for schedule in schedules:
            schedule_id = str(schedule["schedule_id"])
            try:
                result = await client.trigger_evaluation(schedule_id=schedule_id)
                eval_data = result.get("evaluation", {})

                tested += 1
                if eval_data.get("ready"):
                    ready_count += 1
                    print(f"  ✓ {schedule_id[:8]}... - READY")
                else:
                    reason = eval_data.get("blocking_reason", "unknown")
                    print(f"  ✗ {schedule_id[:8]}... - BLOCKED ({reason})")

            except Exception as e:
                print(f"  ? {schedule_id[:8]}... - ERROR: {e}")

        print(f"\nResults: {ready_count}/{tested} ready for advancement")

    except Exception as e:
        fmt.print_error(f"Error in batch test: {e}")


async def view_evaluation_results(client: RuleAPIClient) -> None:
    """View past evaluation results from database."""
    fmt = TableFormatter()
    fmt.print_header("View Evaluation Results")

    try:
        schedule_id = input("Enter schedule_id: ").strip()

        query = """
            SELECT
                execution_id,
                execution_status,
                from_stage_id,
                to_stage_id,
                evaluation_results,
                executed_at,
                failure_reason
            FROM advancement_executions
            WHERE schedule_id = $1
            ORDER BY executed_at DESC
        """

        results = await query_database(query, (schedule_id,))

        if not results:
            fmt.print_warning(f"No evaluation results found for {schedule_id}")
            return

        fmt.print_info(f"Found {len(results)} evaluation(s)")

        for result in results:
            print(f"\nExecution ID: {result['execution_id']}")
            print(f"Status: {result['execution_status']}")
            print(f"From Stage: {result['from_stage_id']}")
            print(f"To Stage: {result['to_stage_id']}")
            print(f"Executed At: {result['executed_at']}")

            if result["failure_reason"]:
                print(f"Failure Reason: {result['failure_reason']}")

            if result["evaluation_results"]:
                print("\nEvaluation Results:")
                print(json.dumps(result["evaluation_results"], indent=2))

            print("-" * 60)

    except Exception as e:
        fmt.print_error(f"Error viewing results: {e}")


# ============================================================================
# Monitoring Functions
# ============================================================================


async def show_statistics_dashboard(client: RuleAPIClient) -> None:
    """Display advancement system statistics."""
    fmt = TableFormatter()
    fmt.print_header("Advancement Statistics Dashboard")

    try:
        stats = await client.get_stats()

        print("System Overview:")
        print(f"  Active Rules: {stats.get('active_rules', 0)}")
        print(f"  Pending Evaluations: {stats.get('pending_evaluations', 0)}")

        print("\nExecutions (Last 30 Days):")
        print(f"  Total: {stats.get('total_executions_30d', 0)}")
        print(f"  ✓ Successes: {stats.get('success_count', 0)}")
        print(f"  ✗ Failures: {stats.get('failed_count', 0)}")
        print(f"  ⊗ Dry Runs: {stats.get('dry_run_count', 0)}")
        print(f"  ⨯ Rejections: {stats.get('rejected_count', 0)}")

        recent_failures = stats.get("recent_failures", [])
        if recent_failures:
            print("\nRecent Failures:")
            for failure in recent_failures[:5]:
                print(f"  • {failure['executed_at'][:10]}")
                print(f"    Schedule: {failure['schedule_id'][:8]}...")
                print(f"    Reason: {failure['failure_reason']}")

    except Exception as e:
        fmt.print_error(f"Error fetching statistics: {e}")


async def show_recent_executions(client: RuleAPIClient) -> None:
    """Show recent advancement executions."""
    fmt = TableFormatter()
    fmt.print_header("Recent Executions")

    try:
        limit = input("Number of recent executions (default: 20): ").strip() or "20"
        limit = int(limit)

        query = """
            SELECT
                execution_id,
                schedule_id,
                execution_status,
                executed_at
            FROM advancement_executions
            ORDER BY executed_at DESC
            LIMIT $1
        """

        executions = await query_database(query, (limit,))

        if not executions:
            fmt.print_warning("No executions found")
            return

        headers = ["Execution ID", "Schedule ID", "Status", "Executed At"]
        rows = []

        for ex in executions:
            rows.append(
                [
                    str(ex["execution_id"])[:8] + "...",
                    str(ex["schedule_id"])[:8] + "...",
                    ex["execution_status"],
                    str(ex["executed_at"])[:19],
                ]
            )

        fmt.print_table(headers, rows)

    except Exception as e:
        fmt.print_error(f"Error fetching executions: {e}")


async def show_dry_run_results(client: RuleAPIClient) -> None:
    """Show dry-run execution results."""
    fmt = TableFormatter()
    fmt.print_header("Dry-Run Results")

    try:
        limit = input("Number of dry-run results (default: 20): ").strip() or "20"
        limit = int(limit)

        query = """
            SELECT execution_id, schedule_id, application_id,
                   from_stage_id, to_stage_id, executed_at
            FROM advancement_executions
            WHERE execution_status = 'dry_run'
            ORDER BY executed_at DESC
            LIMIT $1
        """

        results = await query_database(query, (limit,))

        if not results:
            fmt.print_info("No dry-run results found")
            return

        fmt.print_info(f"Showing {len(results)} dry-run execution(s)")

        for result in results:
            print(f"\n  Schedule: {result['schedule_id']}")
            print(f"  Application: {result['application_id']}")
            from_stage = result["from_stage_id"][:8]
            to_stage = result["to_stage_id"][:8]
            print(f"  Would advance: {from_stage}... → {to_stage}...")
            print(f"  Executed: {result['executed_at']}")

    except Exception as e:
        fmt.print_error(f"Error fetching dry-run results: {e}")


async def compare_dry_run_vs_production() -> None:
    """Compare what would happen in dry-run vs what actually happened."""
    fmt = TableFormatter()
    fmt.print_header("Dry-Run vs Production Comparison")

    try:
        fmt.print_info("This feature compares dry-run executions with actual executions")
        fmt.print_info("for the same schedule to see if predictions matched reality.\n")

        # Find schedules with both dry_run and success/failed executions
        query = """
            SELECT
                schedule_id,
                COUNT(*) FILTER (WHERE execution_status = 'dry_run') as dry_run_count,
                COUNT(*) FILTER (WHERE execution_status IN ('success', 'failed')) as real_count
            FROM advancement_executions
            GROUP BY schedule_id
            HAVING COUNT(*) FILTER (WHERE execution_status = 'dry_run') > 0
               AND COUNT(*) FILTER (WHERE execution_status IN ('success', 'failed')) > 0
            LIMIT 10
        """

        schedules = await query_database(query)

        if not schedules:
            fmt.print_warning("No schedules found with both dry-run and real executions")
            return

        print(f"Found {len(schedules)} schedule(s) with both dry-run and real executions:\n")

        for schedule in schedules:
            schedule_id = schedule["schedule_id"]
            print(f"Schedule: {schedule_id}")
            print(f"  Dry-run executions: {schedule['dry_run_count']}")
            print(f"  Real executions: {schedule['real_count']}")
            print()

    except Exception as e:
        fmt.print_error(f"Error comparing executions: {e}")


# ============================================================================
# Utility Functions
# ============================================================================


async def check_health(client: RuleAPIClient) -> bool:
    """Check application health."""
    fmt = TableFormatter()
    try:
        health = await client.health_check()
        fmt.print_success(f"Health check passed: {health.get('status')}")
        print(f"  Database: {health.get('database')}")
        print(f"  Scheduler: {health.get('scheduler', 'unknown')}")
        return True
    except Exception as e:
        fmt.print_error(f"Health check failed: {e}")
        return False


async def switch_environment() -> str:
    """Prompt for new environment URL and validate."""
    fmt = TableFormatter()
    fmt.print_header("Switch Environment")

    print("Current presets:")
    print("  1. Localhost (http://localhost:8000)")
    print("  2. Staging (https://staging.onrender.com)")
    print("  3. Production (https://production.onrender.com)")
    print("  4. Custom URL")

    choice = input("\nSelect environment: ").strip()

    url_map = {
        "1": "http://localhost:8000",
        "2": "https://staging.onrender.com",
        "3": "https://production.onrender.com",
    }

    if choice in url_map:
        new_url = url_map[choice]
    elif choice == "4":
        new_url = input("Enter custom URL: ").strip()
    else:
        fmt.print_error("Invalid choice")
        return ""

    # Validate by checking health
    fmt.print_info(f"Testing connection to {new_url}...")
    client = RuleAPIClient(new_url)

    if await check_health(client):
        fmt.print_success(f"Switched to {new_url}")
        return new_url
    else:
        fmt.print_error("Failed to connect. Keeping current environment.")
        return ""


async def show_dry_run_status(client: RuleAPIClient) -> None:
    """Display current dry-run mode status from server."""
    fmt = TableFormatter()
    fmt.print_header("Server Dry-Run Status")

    fmt.print_info("Checking server configuration...")
    fmt.print_warning("Note: This checks based on recent executions, not the actual config setting")

    try:
        # Check recent executions to infer dry-run status
        query = """
            SELECT execution_status, COUNT(*) as count
            FROM advancement_executions
            WHERE executed_at > NOW() - INTERVAL '1 hour'
            GROUP BY execution_status
        """

        results = await query_database(query)

        if not results:
            fmt.print_warning("No recent executions found (last 1 hour)")
            return

        for result in results:
            print(f"  {result['execution_status']}: {result['count']}")

        # If we see any dry_run statuses, likely enabled
        has_dry_run = any(r["execution_status"] == "dry_run" for r in results)
        has_real = any(r["execution_status"] in ("success", "failed") for r in results)

        if has_dry_run and not has_real:
            fmt.print_info("Server appears to be in DRY-RUN mode")
        elif has_real and not has_dry_run:
            fmt.print_warning("Server appears to be in PRODUCTION mode")
        else:
            fmt.print_info("Mixed mode detected - check server configuration")

    except Exception as e:
        fmt.print_error(f"Error checking dry-run status: {e}")


# ============================================================================
# Main Menu & Interactive Loop
# ============================================================================


async def show_menu(base_url: str, config: dict[str, Any] | None) -> None:
    """Display main menu."""
    fmt = TableFormatter()
    fmt.print_header("Advancement Rules Testing", width=70)

    config_name = config.get("name", "None") if config else "None"

    print(f"  Environment: {base_url}")
    print(f"  Config: {config_name}")
    print(f"{'=' * 70}\n")

    print("CONFIGURATION")
    print("  1. Select/Load config file")
    print("  2. View current config")
    print("  3. Edit config values")

    print("\nRULE MANAGEMENT")
    print("  4. Create new rule (wizard)")
    print("  5. List all rules")
    print("  6. View rule details")
    print("  7. Delete rule")

    print("\nTESTING & EVALUATION")
    print("  8. Test rule against candidate")
    print("  9. Test all rules (batch)")
    print(" 10. View evaluation results")

    print("\nMONITORING")
    print(" 11. View statistics dashboard")
    print(" 12. Check recent executions")
    print(" 13. View dry-run results")
    print(" 14. Compare dry-run vs production")

    print("\nUTILITIES")
    print(" 15. Health check")
    print(" 16. Switch environment")
    print(" 17. Check server dry-run status")

    print("\n  q. Quit")


async def interactive_menu(base_url: str, initial_config: dict[str, Any] | None = None) -> None:
    """Main interactive menu loop."""
    fmt = TableFormatter()
    client = RuleAPIClient(base_url)
    config = initial_config

    # Initial health check
    fmt.print_info("Checking connection...")
    if not await check_health(client):
        fmt.print_error("Failed to connect to server. Please check the URL and try again.")
        return

    while True:
        await show_menu(base_url, config)

        try:
            choice = input("\nSelect option: ").strip()

            if choice.lower() == "q":
                print("Goodbye!")
                break

            # Configuration
            elif choice == "1":
                config = select_config()
            elif choice == "2":
                view_config(config)
            elif choice == "3":
                config = edit_config(config)

            # Rule Management
            elif choice == "4":
                await create_rule_wizard(client, config)
            elif choice == "5":
                await list_rules_display(client)
            elif choice == "6":
                await view_rule_details(client)
            elif choice == "7":
                await delete_rule_interactive(client)

            # Testing & Evaluation
            elif choice == "8":
                await test_against_candidate(client)
            elif choice == "9":
                await batch_test_rules(client)
            elif choice == "10":
                await view_evaluation_results(client)

            # Monitoring
            elif choice == "11":
                await show_statistics_dashboard(client)
            elif choice == "12":
                await show_recent_executions(client)
            elif choice == "13":
                await show_dry_run_results(client)
            elif choice == "14":
                await compare_dry_run_vs_production()

            # Utilities
            elif choice == "15":
                await check_health(client)
            elif choice == "16":
                new_url = await switch_environment()
                if new_url:
                    base_url = new_url
                    client = RuleAPIClient(base_url)
            elif choice == "17":
                await show_dry_run_status(client)

            else:
                fmt.print_error("Invalid option")

            input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            break
        except Exception as e:
            fmt.print_error(f"Unexpected error: {e}")
            input("\nPress Enter to continue...")


# ============================================================================
# Main Entry Point
# ============================================================================


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive advancement rules testing script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--url",
        help=f"Base URL for testing (default: $TEST_BASE_URL or {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--config",
        help="Path to config file to load (optional)",
    )

    args = parser.parse_args()

    # Determine base URL
    base_url = args.url or os.getenv("TEST_BASE_URL") or DEFAULT_BASE_URL

    # Load initial config if provided
    initial_config = None
    if args.config:
        try:
            config_path = Path(args.config)
            initial_config = ConfigManager.load_config(config_path)
            print(f"Loaded config: {initial_config['name']}")
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)

    # Run interactive menu
    asyncio.run(interactive_menu(base_url, initial_config))


if __name__ == "__main__":
    main()

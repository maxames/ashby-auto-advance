#!/usr/bin/env python3
"""Manual E2E testing script for development.

Usage:
    python scripts/manual_e2e.py                    # Interactive menu (localhost:8000)
    python scripts/manual_e2e.py --scenario panel   # Run specific scenario
    python scripts/manual_e2e.py --replay file.json # Replay webhook
    python scripts/manual_e2e.py --url https://staging.onrender.com  # Test against staging
    TEST_BASE_URL=https://staging.onrender.com python scripts/manual_e2e.py  # Via env var
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configuration with fallbacks
DEFAULT_BASE_URL = "http://localhost:8000"
WEBHOOK_SECRET = os.getenv("ASHBY_WEBHOOK_SECRET", "test_webhook_secret")


def sign_payload(body: str) -> str:
    """Compute Ashby webhook signature.

    Returns signature in Ashby format: "sha256=<hex_digest>"
    """
    hex_digest = hmac.new(
        WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return f"sha256={hex_digest}"


def print_header(text: str):
    """Print section header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_step(number: int, text: str):
    """Print step description."""
    print(f"\n[Step {number}] {text}")


def print_success(text: str):
    """Print success message."""
    print(f"✓ {text}")


def print_error(text: str):
    """Print error message."""
    print(f"✗ {text}")


async def send_webhook(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    """Send webhook to server with signature."""
    body = json.dumps(payload)
    signature = sign_payload(body)

    response = await client.post(
        "/webhooks/ashby",
        content=body,
        headers={
            "Content-Type": "application/json",
            "Ashby-Signature": signature,
        },
    )
    return response


async def check_health(client: httpx.AsyncClient):
    """Check application health."""
    try:
        response = await client.get("/health")
        if response.status_code == 200:
            data = response.json()
            print_success(f"Health check passed: {data.get('status')}")
            print(f"  Database: {data.get('database')}")
            print(f"  Scheduler: {data.get('scheduler', 'unknown')}")
            return True
        else:
            print_error(f"Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Health check error: {e}")
        return False


async def scenario_single_interviewer_pass(base_url: str):
    """Test: Single interviewer passes → advance."""
    print_header("Scenario: Single Interviewer Pass")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        print_step(1, "Check application health")
        if not await check_health(client):
            return

        print_step(2, "Send webhook: Schedule interview")
        schedule_id = str(uuid4())
        event_id = str(uuid4())
        application_id = str(uuid4())

        payload = {
            "action": "interviewScheduleUpdate",
            "data": {
                "interviewSchedule": {
                    "id": schedule_id,
                    "status": "Scheduled",
                    "applicationId": application_id,
                    "candidateId": str(uuid4()),
                    "interviewStageId": str(uuid4()),
                    "interviewEvents": [
                        {
                            "id": event_id,
                            "interviewId": str(uuid4()),
                            "startTime": datetime.now(UTC).isoformat(),
                            "endTime": (
                                datetime.now(UTC) + timedelta(hours=1)
                            ).isoformat(),
                            "feedbackLink": "https://ashby.com/feedback",
                            "location": "Zoom",
                            "meetingLink": "https://zoom.us/j/test",
                            "hasSubmittedFeedback": False,
                            "createdAt": datetime.now(UTC).isoformat(),
                            "updatedAt": datetime.now(UTC).isoformat(),
                            "extraData": {},
                            "interviewers": [
                                {
                                    "id": str(uuid4()),
                                    "firstName": "Test",
                                    "lastName": "Interviewer",
                                    "email": "test@example.com",
                                    "globalRole": "Interviewer",
                                    "trainingRole": "Trained",
                                    "isEnabled": True,
                                    "updatedAt": datetime.now(UTC).isoformat(),
                                    "interviewerPool": {
                                        "id": str(uuid4()),
                                        "title": "Test Pool",
                                        "isArchived": False,
                                        "trainingPath": {},
                                    },
                                }
                            ],
                        }
                    ],
                }
            },
        }

        response = await send_webhook(client, payload)
        if response.status_code == 200:
            print_success(f"Webhook accepted: {response.status_code}")
            print(f"  Schedule ID: {schedule_id}")
            print(f"  Application ID: {application_id}")
        else:
            print_error(f"Webhook failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return

        print_step(3, "Send webhook: Mark complete with passing feedback")
        payload["data"]["interviewSchedule"]["status"] = "Complete"
        payload["data"]["interviewSchedule"]["interviewEvents"][0][
            "hasSubmittedFeedback"
        ] = True

        response = await send_webhook(client, payload)
        if response.status_code == 200:
            print_success(f"Status update accepted: {response.status_code}")
        else:
            print_error(f"Status update failed: {response.status_code}")

        print("\n" + "=" * 60)
        print("Next steps:")
        print("  1. Check application logs for webhook processing")
        print("  2. Wait for advancement evaluation (runs every 15 min)")
        print("  3. Check advancement_executions table for results")
        print("=" * 60)


async def scenario_panel_all_pass(base_url: str):
    """Test: Panel (3 interviewers) all pass → advance."""
    print_header("Scenario: Panel Interview - All Pass")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        print_step(1, "Check application health")
        if not await check_health(client):
            return

        print_step(2, "Send webhook: Schedule panel interview (3 interviewers)")
        schedule_id = str(uuid4())

        # Create 3 interviewers
        interviewers = []
        for i in range(3):
            interviewers.append(
                {
                    "id": str(uuid4()),
                    "firstName": f"Interviewer_{i+1}",
                    "lastName": "Test",
                    "email": f"interviewer{i+1}@example.com",
                    "globalRole": "Interviewer",
                    "trainingRole": "Trained",
                    "isEnabled": True,
                    "updatedAt": datetime.now(UTC).isoformat(),
                    "interviewerPool": {
                        "id": str(uuid4()),
                        "title": "Test Pool",
                        "isArchived": False,
                        "trainingPath": {},
                    },
                }
            )

        payload = {
            "action": "interviewScheduleUpdate",
            "data": {
                "interviewSchedule": {
                    "id": schedule_id,
                    "status": "Scheduled",
                    "applicationId": str(uuid4()),
                    "candidateId": str(uuid4()),
                    "interviewStageId": str(uuid4()),
                    "interviewEvents": [
                        {
                            "id": str(uuid4()),
                            "interviewId": str(uuid4()),
                            "startTime": datetime.now(UTC).isoformat(),
                            "endTime": (
                                datetime.now(UTC) + timedelta(hours=1)
                            ).isoformat(),
                            "feedbackLink": "https://ashby.com/feedback",
                            "location": "Zoom",
                            "meetingLink": "https://zoom.us/j/test",
                            "hasSubmittedFeedback": False,
                            "createdAt": datetime.now(UTC).isoformat(),
                            "updatedAt": datetime.now(UTC).isoformat(),
                            "extraData": {},
                            "interviewers": interviewers,
                        }
                    ],
                }
            },
        }

        response = await send_webhook(client, payload)
        if response.status_code == 200:
            print_success(f"Panel interview scheduled: {schedule_id}")
            print(f"  Interviewers: {len(interviewers)}")
        else:
            print_error(f"Webhook failed: {response.status_code}")
            return

        print_step(3, "Mark complete (all 3 interviewers submit)")
        payload["data"]["interviewSchedule"]["status"] = "Complete"
        payload["data"]["interviewSchedule"]["interviewEvents"][0][
            "hasSubmittedFeedback"
        ] = True

        response = await send_webhook(client, payload)
        if response.status_code == 200:
            print_success("Panel interview marked complete")
        else:
            print_error(f"Failed: {response.status_code}")

        print("\n" + "=" * 60)
        print("This scenario requires:")
        print("  - Advancement rule configured for this interview")
        print("  - All 3 interviewers must submit passing feedback")
        print("  - Wait 30+ minutes after last feedback submission")
        print("=" * 60)


async def scenario_panel_one_fails(base_url: str):
    """Test: Panel (2 pass, 1 fail) → rejection."""
    print_header("Scenario: Panel Interview - One Fails")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        print_step(1, "Check application health")
        if not await check_health(client):
            return

        print("This scenario is similar to 'panel_all_pass' but requires:")
        print("  - One interviewer submits failing score (< threshold)")
        print("  - System should send rejection notification")
        print("  - No advancement should occur")
        print("\nNote: Feedback submission is handled through Ashby UI")
        print("      This script only simulates the webhook flow")


async def replay_webhook(file_path: str, base_url: str):
    """Replay a webhook payload from JSON file."""
    print_header(f"Replaying Webhook: {file_path}")

    try:
        with open(file_path) as f:
            payload = json.load(f)

        print_step(1, "Loaded webhook payload")
        print(f"  Action: {payload.get('action')}")

        if "data" in payload and "interviewSchedule" in payload["data"]:
            schedule_id = payload["data"]["interviewSchedule"].get("id")
            status = payload["data"]["interviewSchedule"].get("status")
            print(f"  Schedule ID: {schedule_id}")
            print(f"  Status: {status}")

        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            print_step(2, f"Sending to {base_url}")
            response = await send_webhook(client, payload)

            if response.status_code == 200:
                print_success(f"Webhook accepted: {response.status_code}")
            else:
                print_error(f"Webhook failed: {response.status_code}")
                print(f"  Response: {response.text}")

    except FileNotFoundError:
        print_error(f"File not found: {file_path}")
    except json.JSONDecodeError:
        print_error(f"Invalid JSON in file: {file_path}")
    except Exception as e:
        print_error(f"Error: {e}")


async def interactive_menu(base_url: str):
    """Show interactive menu of scenarios."""
    print_header(f"E2E Testing - {base_url}")

    scenarios = {
        "1": ("Single interviewer pass", scenario_single_interviewer_pass),
        "2": ("Panel all pass", scenario_panel_all_pass),
        "3": ("Panel one fails", scenario_panel_one_fails),
        "4": ("Health check only", check_health_only),
    }

    while True:
        print("\nAvailable scenarios:")
        for key, (name, _) in scenarios.items():
            print(f"  {key}. {name}")
        print("  q. Quit")

        choice = input("\nSelect scenario (or 'q' to quit): ").strip()

        if choice.lower() == "q":
            print("Goodbye!")
            break

        if choice in scenarios:
            _, func = scenarios[choice]
            try:
                if choice == "4":
                    async with httpx.AsyncClient(
                        base_url=base_url, timeout=30.0
                    ) as client:
                        await check_health(client)
                else:
                    await func(base_url)
            except KeyboardInterrupt:
                print("\n\nInterrupted by user")
                break
            except Exception as e:
                print_error(f"Scenario failed: {e}")
        else:
            print_error("Invalid choice")


async def check_health_only(base_url: str):
    """Just check health endpoint."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        await check_health(client)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manual E2E testing for Ashby Auto-Advance"
    )
    parser.add_argument(
        "--scenario",
        choices=["single", "panel", "rejection", "health"],
        help="Run specific scenario",
    )
    parser.add_argument("--replay", help="Path to webhook JSON file to replay")
    parser.add_argument(
        "--url",
        help=f"Base URL for testing (default: $TEST_BASE_URL or {DEFAULT_BASE_URL})",
    )

    args = parser.parse_args()

    # Determine base URL: CLI arg > env var > default
    base_url = args.url or os.getenv("TEST_BASE_URL") or DEFAULT_BASE_URL

    if args.replay:
        asyncio.run(replay_webhook(args.replay, base_url))
    elif args.scenario:
        scenario_map = {
            "single": scenario_single_interviewer_pass,
            "panel": scenario_panel_all_pass,
            "rejection": scenario_panel_one_fails,
            "health": check_health_only,
        }
        asyncio.run(scenario_map[args.scenario](base_url))
    else:
        asyncio.run(interactive_menu(base_url))


if __name__ == "__main__":
    main()

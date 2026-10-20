#!/usr/bin/env python3
"""End-to-end test: run the real workflow in a real n8n against mock HubSpot + Slack.

    python test/run_tests.py --n8n /path/to/node_modules/.bin/n8n

Starts mock services, starts n8n with a throwaway data folder, imports the
workflow (pointed at the mocks) and credentials, publishes it, then sends
leads to the live webhook and checks the response, the CRM state and every
API call. Writes docs/test-report.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test"))
sys.path.insert(0, str(ROOT / "workflow"))

import build_workflow  # noqa: E402
import mock_services  # noqa: E402

MOCK = "http://127.0.0.1:8999"
N8N_PORT = 5690  # not 5679: that is n8n's internal task-broker port
WEBHOOK = f"http://127.0.0.1:{N8N_PORT}/webhook/lead-intake"
SECRET = "test-form-secret"
NURTURE_LIST = "1234"


# ---------------------------------------------------------------- helpers

# Everything here is local; never send it through an HTTP(S)_PROXY from the environment.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def http(method: str, url: str, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        try:
            return err.code, json.loads(raw)
        except json.JSONDecodeError:
            return err.code, raw


def send_lead(lead: dict, secret: str | None = SECRET):
    headers = {"X-Webhook-Secret": secret} if secret else {}
    return http("POST", WEBHOOK, lead, headers)


def state() -> dict:
    return http("GET", f"{MOCK}/_state")[1]


def contact_by_email(email: str):
    for cid, c in state()["contacts"].items():
        if c.get("email") == email:
            return cid, c
    return None, None


def hubspot_calls(since: int) -> list[dict]:
    return [c for c in state()["calls"][since:] if c["path"].startswith("/crm/")]


# ---------------------------------------------------------------- n8n lifecycle

class N8n:
    def __init__(self, binary: str):
        self.binary = binary
        self.home = Path(tempfile.mkdtemp(prefix="n8n-test-"))
        self.env = {
            **os.environ,
            "N8N_USER_FOLDER": str(self.home),
            "N8N_PORT": str(N8N_PORT),
            "N8N_HOST": "127.0.0.1",
            "N8N_LISTEN_ADDRESS": "127.0.0.1",
            "N8N_ENCRYPTION_KEY": "test-encryption-key-not-secret",
            "N8N_DIAGNOSTICS_ENABLED": "false",
            "N8N_PERSONALIZATION_ENABLED": "false",
            "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
            "N8N_SECURE_COOKIE": "false",
            "N8N_LOG_LEVEL": "warn",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
        self.proc = None

    def cli(self, *args: str) -> str:
        result = subprocess.run([self.binary, *args], env=self.env, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"n8n {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
        return result.stdout

    def start(self) -> None:
        log = open(self.home / "n8n.log", "w")
        self.proc = subprocess.Popen([self.binary, "start"], env=self.env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                # /healthz is up before workflows are activated, so wait for the webhook itself
                # (an unauthenticated probe gets 403 once it is registered, 404 before).
                if http("POST", WEBHOOK, {}, timeout=2)[0] != 404:
                    return
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            if self.proc.poll() is not None:
                break
            time.sleep(1)
        raise RuntimeError("n8n did not start:\n" + (self.home / "n8n.log").read_text()[-3000:])

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def setup(n8n: N8n) -> None:
    workflow = build_workflow.build(MOCK, f"{MOCK}/slack/T000/B000/test", NURTURE_LIST)
    wf_file = n8n.home / "workflow.json"
    wf_file.write_text(json.dumps(workflow))
    creds = [
        {**build_workflow.CRED_WEBHOOK, "type": "httpHeaderAuth",
         "data": {"name": "X-Webhook-Secret", "value": SECRET}},
        {**build_workflow.CRED_HUBSPOT, "type": "httpHeaderAuth",
         "data": {"name": "Authorization", "value": mock_services.TOKEN}},
    ]
    cred_file = n8n.home / "credentials.json"
    cred_file.write_text(json.dumps(creds))
    n8n.cli("import:credentials", f"--input={cred_file}")
    n8n.cli("import:workflow", f"--input={wf_file}")
    n8n.cli("publish:workflow", f"--id={build_workflow.WORKFLOW_ID}")


# ---------------------------------------------------------------- scenarios

HOT = {
    "name": "  jane   O'NEILL ", "email": "  Jane.ONeill@Acme-Robotics.com ", "phone": "(415) 555-0134",
    "company": "Acme Robotics", "job_title": "VP Marketing", "country": "usa", "employees": "250",
    "budget": "$12,000", "form": "demo_request", "marketing_consent": "yes",
    "utm": {"source": "LinkedIn", "medium": "cpc", "campaign": "Q4-Demo"},
    "message": "We need to automate our lead routing before the Q4 launch.",
}


def scenarios():
    def hot_new(r):
        status, body = send_lead(HOT)
        cid, c = contact_by_email("jane.oneill@acme-robotics.com")
        slack = state()["slack"]
        r.check(status == 200 and body["action"] == "created", "201-style create, 200 to the form", (status, body))
        r.check(body["tier"] == "hot" and body["score"] >= 60, f"scored hot ({body.get('score')}/100)", body)
        r.check(c and c["firstname"] == "Jane" and c["lastname"] == "O'Neill", "name split + title-cased", c)
        r.check(c["phone"] == "+14155550134" and c["country"] == "United States", "phone E.164 + country normalised", c)
        r.check(c["website"] == "acme-robotics.com", "website derived from business email", c)
        r.check(c["latest_utm_source"] == "linkedin" and c["latest_utm_campaign"] == "q4-demo", "UTMs captured", c)
        r.check(c["lifecyclestage"] == "marketingqualifiedlead" and c["hs_lead_status"] == "NEW", "MQL + NEW", c)
        r.check(any("Hot lead" in s["text"] and "jane.oneill@acme-robotics.com" in s["text"] for s in slack),
                "sales alerted in Slack", slack)
        return {"response": body, "contact": c}

    def duplicate(r):
        before = len(state()["contacts"])
        status, body = send_lead({**HOT, "email": "JANE.ONEILL@acme-robotics.com", "name": "Jane O'Neill"})
        r.check(status == 200 and body["action"] == "updated", "same person again -> updated, not duplicated", body)
        r.check(len(state()["contacts"]) == before, "no duplicate contact created", len(state()["contacts"]))
        return {"response": body}

    def existing_update(r):
        status, body = send_lead({
            "first_name": "maria", "last_name": "", "email": "maria.garcia@northwind.io", "job_title": "Marketing Manager",
            "phone": "+44 20 7946 0958", "form": "newsletter", "utm_source": "newsletter", "utm_medium": "email",
        })
        cid, c = contact_by_email("maria.garcia@northwind.io")
        r.check(status == 200 and body["action"] == "updated" and cid == "101", "matched existing contact 101", body)
        r.check(c["lastname"] == "Garcia" and c["jobtitle"] == "Head of Growth",
                "existing data not wiped or overwritten", c)
        r.check(c["phone"] == "+442079460958", "new phone added", c)
        r.check(c["lifecyclestage"] == "salesqualifiedlead", "lifecycle NOT moved backwards (SQL kept)", c)
        r.check(c["latest_utm_source"] == "newsletter", "latest attribution refreshed", c)
        return {"response": body, "contact": c}

    def warm(r):
        status, body = send_lead({"name": "Sam Lee", "email": "sam@brightpath.co", "job_title": "Marketing Manager",
                                  "company": "Brightpath", "form": "contact_sales", "country": "Canada"})
        r.check(status == 200 and body["tier"] == "warm", f"scored warm ({body.get('score')}/100)", body)
        r.check(body["contactId"] in state()["lists"].get(NURTURE_LIST, []), "added to HubSpot nurture list", state()["lists"])
        return {"response": body}

    def cold(r):
        slack_before = len(state()["slack"])
        status, body = send_lead({"name": "alex", "email": "alex.k@gmail.com", "form": "newsletter"})
        r.check(status == 200 and body["tier"] == "cold" and body["action"] == "created", "cold lead saved", body)
        r.check(len(state()["slack"]) == slack_before, "no Slack noise for cold leads", state()["slack"][slack_before:])
        return {"response": body}

    def invalid(r):
        calls = len(state()["calls"])
        status, body = send_lead({"name": "Bad Data", "email": "not-an-email", "phone": "12"})
        r.check(status == 422 and body["status"] == "rejected", "rejected with 422", (status, body))
        r.check(any("not a valid address" in e for e in body["errors"]), "error explains why", body)
        r.check(hubspot_calls(calls) == [], "nothing sent to HubSpot", hubspot_calls(calls))
        return {"response": body}

    def no_secret(r):
        status, body = send_lead({"email": "spam@spam.com"}, secret=None)
        r.check(status in (401, 403), f"request without secret refused ({status})", body)
        status, body = send_lead({"email": "spam@spam.com"}, secret="wrong")
        r.check(status in (401, 403), f"request with wrong secret refused ({status})", body)
        r.check(contact_by_email("spam@spam.com")[0] is None, "nothing saved", None)
        return {"response": status}

    def crm_outage(r):
        calls = len(state()["calls"])
        http("POST", f"{MOCK}/_fail", {"path": "/crm/v3/objects/contacts", "method": "POST", "status": 500, "times": 10})
        status, body = send_lead({"name": "Priya Shah", "email": "priya@orbitlabs.ai", "job_title": "CEO",
                                  "form": "demo_request"})
        creates = [c for c in hubspot_calls(calls) if c["path"] == "/crm/v3/objects/contacts" and c["method"] == "POST"]
        slack = state()["slack"]
        r.check(status == 502 and body["status"] == "error", "form told the CRM sync failed (502)", (status, body))
        r.check(len(creates) == 3, f"retried {len(creates)}x before giving up", len(creates))
        r.check(any("HubSpot sync failed for priya@orbitlabs.ai" in s["text"] for s in slack), "ops alerted in Slack", slack[-1:])
        http("POST", f"{MOCK}/_reset_failures", {})
        return {"response": body}

    def nurture_outage(r):
        http("POST", f"{MOCK}/_fail", {"path": f"/crm/v3/lists/{NURTURE_LIST}/memberships/add", "status": 500, "times": 10})
        status, body = send_lead({"name": "Tom Reed", "email": "tom@fieldnote.studio", "job_title": "Marketing Lead",
                                  "form": "contact_sales"})
        slack = state()["slack"]
        r.check(status == 200 and body["action"] == "created", "lead still saved when the list call fails", (status, body))
        r.check(any("Couldn't add tom@fieldnote.studio to the nurture list" in s["text"] for s in slack),
                "ops alerted about the nurture failure", slack[-1:])
        return {"response": body}

    return [
        ("New hot lead with messy data", hot_new),
        ("Same person submits again", duplicate),
        ("Existing CRM contact fills a form", existing_update),
        ("Warm lead", warm),
        ("Cold lead", cold),
        ("Invalid email", invalid),
        ("Missing / wrong webhook secret", no_secret),
        ("HubSpot outage on create", crm_outage),
        ("Nurture list API fails", nurture_outage),
    ]


class Result:
    def __init__(self, name: str):
        self.name = name
        self.checks: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, label: str, detail) -> None:
        self.checks.append((bool(ok), label, json.dumps(detail, default=str)[:400]))

    @property
    def passed(self) -> bool:
        return all(ok for ok, _, _ in self.checks) and bool(self.checks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n8n", default=shutil.which("n8n"), help="path to the n8n binary")
    parser.add_argument("--keep", action="store_true", help="leave n8n running for screenshots")
    args = parser.parse_args()
    if not args.n8n:
        print("n8n binary not found; pass --n8n", file=sys.stderr)
        return 1

    mock_services.serve()
    n8n = N8n(args.n8n)
    print(f"n8n data folder: {n8n.home}")
    results = []
    examples = {}
    try:
        setup(n8n)
        n8n.start()
        for name, fn in scenarios():
            result = Result(name)
            try:
                examples[name] = fn(result)
            except Exception as exc:  # a crash is a failed scenario, not a crashed run
                result.check(False, f"scenario crashed: {exc!r}", None)
            results.append(result)
            mark = "PASS" if result.passed else "FAIL"
            print(f"[{mark}] {name}")
            for ok, label, detail in result.checks:
                print(f"    {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f"\n         {detail}"))
    finally:
        if args.keep:
            print(f"n8n left running on http://127.0.0.1:{N8N_PORT} (pid {n8n.proc.pid})")
            (ROOT / "test" / ".n8n-home").write_text(str(n8n.home))
        else:
            n8n.stop()

    write_report(results, examples)
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} scenarios passed, "
          f"{sum(ok for r in results for ok, _, _ in r.checks)}/{sum(len(r.checks) for r in results)} checks")
    return 0 if passed == len(results) else 1


def write_report(results: list[Result], examples: dict) -> None:
    lines = ["# Test report", "",
             "The real workflow, running in real n8n, against mock HubSpot and Slack APIs that record every call.",
             "Generated by `test/run_tests.py`.", "",
             f"**{sum(r.passed for r in results)}/{len(results)} scenarios passed** "
             f"({sum(ok for r in results for ok, _, _ in r.checks)}/{sum(len(r.checks) for r in results)} checks)", ""]
    for r in results:
        lines.append(f"## {'PASS' if r.passed else 'FAIL'}: {r.name}")
        for ok, label, _ in r.checks:
            lines.append(f"- {'✅' if ok else '❌'} {label}")
        lines.append("")
    hot = examples.get("New hot lead with messy data")
    if hot:
        lines += ["## Example: what the form sent vs. what reached HubSpot", "", "Sent:", "```json",
                  json.dumps(HOT, indent=2), "```", "", "Saved in HubSpot:", "```json",
                  json.dumps(hot["contact"], indent=2), "```", "", "Returned to the form:", "```json",
                  json.dumps(hot["response"], indent=2), "```", ""]
    (ROOT / "docs" / "test-report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

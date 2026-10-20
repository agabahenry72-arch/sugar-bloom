#!/usr/bin/env python3
"""Assemble the n8n workflow JSON from the readable sources in ../code/.

    python workflow/build_workflow.py                 # writes workflow/lead-to-hubspot.json
    python workflow/build_workflow.py --hubspot-url http://127.0.0.1:8999 \
        --slack-url http://127.0.0.1:8999/slack/test -o /tmp/test.json   # test build

The Code-node logic lives in ../code/*.js so it can be read, reviewed and
diffed like normal code; this script is the only place node wiring is defined.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"

WORKFLOW_ID = "LeadToHubSpot001"
WEBHOOK_ID = "0b7f5c52-3a0e-4f6b-9a37-5d8e2f1c4a10"
CRED_WEBHOOK = {"id": "LeadFormSecret01", "name": "Lead form webhook secret"}
CRED_HUBSPOT = {"id": "HubSpotToken0001", "name": "HubSpot private app token"}

CONFIG_EXPR = "$('Config').first().json"


def uid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"lead-to-hubspot/{name}"))


def node(name: str, type_: str, version: float, position: tuple[int, int], parameters: dict, **extra) -> dict:
    return {"parameters": parameters, "id": uid(name), "name": name, "type": f"n8n-nodes-base.{type_}",
            "typeVersion": version, "position": list(position), **extra}


def code_node(name: str, file: str, position, per_item: bool = False) -> dict:
    params = {"jsCode": (CODE / file).read_text(encoding="utf-8")}
    if per_item:
        params["mode"] = "runOnceForEachItem"
    return node(name, "code", 2, position, params)


def condition(left: str, op_type: str, operation: str, right=None, name: str = "") -> dict:
    cond = {"id": uid(f"cond/{name or left}"), "leftValue": left,
            "operator": {"type": op_type, "operation": operation}}
    if right is None:
        cond["rightValue"] = ""
        cond["operator"]["singleValue"] = True
    else:
        cond["rightValue"] = right
    return {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [cond], "combinator": "and"}


def hubspot_request(name: str, method: str, path_expr: str, body_expr: str, position) -> dict:
    return node(
        name, "httpRequest", 4.2, position,
        {
            "method": method,
            "url": f"={{{{ {CONFIG_EXPR}.hubspotBaseUrl }}}}{path_expr}",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({body_expr}) }}}}",
            "options": {"timeout": 10000},
        },
        credentials={"httpHeaderAuth": CRED_HUBSPOT},
        retryOnFail=True, maxTries=3, waitBetweenTries=1500,
        onError="continueErrorOutput",
    )


def slack_post(name: str, text_expr: str, position, on_error: str = "continueRegularOutput") -> dict:
    return node(
        name, "httpRequest", 4.2, position,
        {
            "method": "POST",
            "url": f"={{{{ {CONFIG_EXPR}.slackWebhookUrl }}}}",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ JSON.stringify({{ text: {text_expr} }}) }}}}",
            "options": {"timeout": 10000},
        },
        retryOnFail=True, maxTries=2, waitBetweenTries=1000, onError=on_error,
    )


def respond(name: str, code: int, body_expr: str, position) -> dict:
    return node(name, "respondToWebhook", 1.1, position,
                {"respondWith": "json", "responseBody": f"={{{{ JSON.stringify({body_expr}) }}}}",
                 "options": {"responseCode": code}})


def build(hubspot_url: str, slack_url: str, nurture_list: str) -> dict:
    lead = "$('Clean & validate lead').item.json.lead"
    nodes = [
        node("Lead form webhook", "webhook", 2, (0, 300),
             {"httpMethod": "POST", "path": "lead-intake", "authentication": "headerAuth",
              "responseMode": "responseNode", "options": {}},
             webhookId=WEBHOOK_ID, credentials={"httpHeaderAuth": CRED_WEBHOOK}),
        node("Config", "set", 3.4, (220, 300), {
            "assignments": {"assignments": [
                {"id": uid("cfg/hubspot"), "name": "hubspotBaseUrl", "value": hubspot_url, "type": "string"},
                {"id": uid("cfg/slack"), "name": "slackWebhookUrl", "value": slack_url, "type": "string"},
                {"id": uid("cfg/list"), "name": "nurtureListId", "value": nurture_list, "type": "string"},
                {"id": uid("cfg/hot"), "name": "hotScore", "value": 60, "type": "number"},
                {"id": uid("cfg/warm"), "name": "warmScore", "value": 30, "type": "number"},
            ]},
            "includeOtherFields": True, "options": {}}),
        code_node("Clean & validate lead", "clean-validate.js", (480, 300)),
        node("Valid lead?", "if", 2.2, (700, 300),
             {"conditions": condition("={{ $json.valid }}", "boolean", "true"), "options": {}}),
        respond("Respond: invalid lead", 422,
                "{ status: 'rejected', errors: $json.errors, warnings: $json.warnings }", (920, 460)),
        code_node("Score lead", "score-lead.js", (920, 200)),
        hubspot_request("HubSpot: find contact", "POST", "/crm/v3/objects/contacts/search",
                        "{ filterGroups: [{ filters: [{ propertyName: 'email', operator: 'EQ', value: $json.lead.email }] }],"
                        " properties: ['email', 'firstname', 'lastname', 'phone', 'company', 'jobtitle', 'website',"
                        " 'country', 'lifecyclestage', 'hs_lead_status'], limit: 1 }", (1140, 200)),
        code_node("Merge with existing contact", "build-hubspot-payload.js", (1360, 200), per_item=True),
        node("New contact?", "if", 2.2, (1580, 200),
             {"conditions": condition("={{ $json.action }}", "string", "equals", "create", "action"), "options": {}}),
        hubspot_request("HubSpot: create contact", "POST", "/crm/v3/objects/contacts",
                        "{ properties: $json.properties }", (1800, 80)),
        hubspot_request("HubSpot: update contact", "PATCH", "/crm/v3/objects/contacts/{{ $json.contactId }}",
                        "{ properties: $json.properties }", (1800, 320)),
        code_node("Result summary", "summary.js", (2040, 200), per_item=True),
        node("Route by tier", "switch", 3.2, (2440, 200), {
            "rules": {"values": [
                {"conditions": condition("={{ $json.tier }}", "string", "equals", tier, f"tier/{tier}"),
                 "renameOutput": True, "outputKey": tier}
                for tier in ("hot", "warm", "cold")
            ]},
            "options": {}}),
        slack_post("Slack: alert sales (hot lead)",
                   "`:fire: Hot lead (${$json.score}/100): ${$json.email}\\n${$json.reasons.join('\\n')}`",
                   (2680, 20)),
        hubspot_request("HubSpot: add to nurture list", "PUT",
                        f"/crm/v3/lists/{{{{ {CONFIG_EXPR}.nurtureListId }}}}/memberships/add",
                        "[ $json.contactId ]", (2680, 220)),
        slack_post("Slack: alert ops (nurture failed)",
                   "`:warning: Couldn't add ${$('Result summary').item.json.email} to the nurture list: "
                   "${$json.error?.message ?? 'unknown error'}`", (2900, 400)),
        respond("Respond: lead saved", 200, "$('Result summary').item.json", (3140, 200)),
        slack_post("Slack: alert ops (CRM error)",
                   f"`:rotating_light: HubSpot sync failed for ${{{lead}.email}}: "
                   f"${{$json.error?.message ?? 'unknown error'}}. Lead NOT saved; retry from n8n executions.`",
                   (2040, 520)),
        respond("Respond: CRM error", 502,
                f"{{ status: 'error', message: 'CRM sync failed; the team has been alerted', email: {lead}.email }}",
                (2240, 520)),
    ]

    def to(*names: str) -> list[dict]:
        return [{"node": n, "type": "main", "index": 0} for n in names]

    connections = {
        "Lead form webhook": {"main": [to("Config")]},
        "Config": {"main": [to("Clean & validate lead")]},
        "Clean & validate lead": {"main": [to("Valid lead?")]},
        "Valid lead?": {"main": [to("Score lead"), to("Respond: invalid lead")]},
        "Score lead": {"main": [to("HubSpot: find contact")]},
        "HubSpot: find contact": {"main": [to("Merge with existing contact"), to("Slack: alert ops (CRM error)")]},
        "Merge with existing contact": {"main": [to("New contact?")]},
        "New contact?": {"main": [to("HubSpot: create contact"), to("HubSpot: update contact")]},
        "HubSpot: create contact": {"main": [to("Result summary"), to("Slack: alert ops (CRM error)")]},
        "HubSpot: update contact": {"main": [to("Result summary"), to("Slack: alert ops (CRM error)")]},
        "Result summary": {"main": [to("Route by tier")]},
        "Route by tier": {"main": [to("Slack: alert sales (hot lead)"), to("HubSpot: add to nurture list"),
                                   to("Respond: lead saved")]},
        "Slack: alert sales (hot lead)": {"main": [to("Respond: lead saved")]},
        "HubSpot: add to nurture list": {"main": [to("Respond: lead saved"), to("Slack: alert ops (nurture failed)")]},
        "Slack: alert ops (nurture failed)": {"main": [to("Respond: lead saved")]},
        "Slack: alert ops (CRM error)": {"main": [to("Respond: CRM error")]},
    }

    notes = [
        ("1. Intake", "Website / ad lead forms POST here.\nProtected by a secret header.", (-80, 120), 460, 380),
        ("2. Data hygiene + scoring", "Trim, case, phone (E.164), country, UTMs.\nInvalid leads get a 422 with reasons.",
         (420, 80), 640, 560),
        ("3. HubSpot upsert", "Search by email -> update or create.\nNever blanks existing data; lifecycle only moves forward.\n"
         "3 retries, then ops alert + 502.", (1080, -40), 1300, 720),
        ("4. Routing", "hot -> Slack alert to sales\nwarm -> HubSpot nurture list\ncold -> saved only", (2400, -100), 900, 660),
    ]
    for i, (title, text, pos, w, h) in enumerate(notes):
        nodes.append(node(f"Note {i + 1}", "stickyNote", 1, pos,
                          {"content": f"## {title}\n{text}", "height": h, "width": w, "color": [7, 5, 4, 6][i]}))

    return {
        "id": WORKFLOW_ID,
        "name": "Lead intake -> HubSpot (clean, score, upsert, route)",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all", "saveDataSuccessExecution": "all",
                     "saveManualExecutions": True},
        "pinData": {},
        "active": False,
        "tags": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hubspot-url", default="https://api.hubapi.com")
    parser.add_argument("--slack-url", default="https://hooks.slack.com/services/REPLACE/WITH/YOURS")
    parser.add_argument("--nurture-list", default="REPLACE_WITH_LIST_ID")
    parser.add_argument("-o", "--output", default=str(ROOT / "workflow" / "lead-to-hubspot.json"))
    args = parser.parse_args()
    workflow = build(args.hubspot_url, args.slack_url, args.nurture_list)
    Path(args.output).write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(workflow['nodes'])} nodes)")


if __name__ == "__main__":
    main()

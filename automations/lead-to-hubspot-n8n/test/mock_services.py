"""Local stand-ins for the HubSpot CRM v3 API and a Slack incoming webhook.

Implements just the endpoints the workflow uses, with HubSpot's real paths,
status codes and response shapes, and records every request so the test can
assert exactly what the workflow sent.

  POST  /crm/v3/objects/contacts/search
  POST  /crm/v3/objects/contacts
  PATCH /crm/v3/objects/contacts/{id}
  PUT   /crm/v3/lists/{listId}/memberships/add
  POST  /slack/*                     (incoming webhook)
  GET   /_state                      (test helper: contacts, list members, calls)
  POST  /_fail                       (test helper: {"path": "...", "status": 500, "times": 1})
  POST  /_reset_failures             (test helper: clear simulated failures)
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "Bearer pat-test-token"

SEED_CONTACTS = {
    "101": {
        "email": "maria.garcia@northwind.io",
        "firstname": "Maria",
        "lastname": "Garcia",
        "company": "Northwind",
        "jobtitle": "Head of Growth",
        "phone": "",
        "lifecyclestage": "salesqualifiedlead",
        "hs_lead_status": "IN_PROGRESS",
    }
}


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.contacts = {k: dict(v) for k, v in SEED_CONTACTS.items()}
        self.lists: dict[str, list[str]] = {}
        self.calls: list[dict] = []
        self.slack: list[dict] = []
        self.failures: list[dict] = []
        self.next_id = 200


STATE = State()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep test output clean
        pass

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw or b"null")
        except json.JSONDecodeError:
            return raw.decode("utf-8", "replace")

    def _send(self, status: int, payload=None) -> None:
        data = json.dumps(payload if payload is not None else {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self, method: str) -> None:
        body = self._body()
        path = self.path.split("?")[0]
        with STATE.lock:
            if path == "/_state":
                return self._send(200, {"contacts": STATE.contacts, "lists": STATE.lists,
                                        "calls": STATE.calls, "slack": STATE.slack})
            if path == "/_reset":
                STATE.reset()
                return self._send(200, {"ok": True})
            if path == "/_fail":
                STATE.failures.append(body)
                return self._send(200, {"ok": True})
            if path == "/_reset_failures":
                STATE.failures.clear()
                return self._send(200, {"ok": True})

            STATE.calls.append({"method": method, "path": path, "body": body,
                                "auth": self.headers.get("Authorization")})
            for failure in STATE.failures:
                if failure["path"] == path and failure.get("method", method) == method and failure["times"] > 0:
                    failure["times"] -= 1
                    return self._send(failure["status"], {"status": "error", "message": "Simulated outage"})

            if path.startswith("/slack/"):
                STATE.slack.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")
                return
            if self.headers.get("Authorization") != TOKEN:
                return self._send(401, {"status": "error", "category": "INVALID_AUTHENTICATION",
                                        "message": "Authentication credentials not found."})
            return self._hubspot(method, path, body)

    def _hubspot(self, method: str, path: str, body) -> None:
        if method == "POST" and path == "/crm/v3/objects/contacts/search":
            email = body["filterGroups"][0]["filters"][0]["value"].lower()
            found = [(cid, c) for cid, c in STATE.contacts.items() if c.get("email", "").lower() == email]
            wanted = body.get("properties") or ["email"]
            results = [{"id": cid, "properties": {p: c.get(p) for p in wanted}, "archived": False}
                       for cid, c in found]
            return self._send(200, {"total": len(results), "results": results})

        if method == "POST" and path == "/crm/v3/objects/contacts":
            props = body["properties"]
            email = props.get("email", "").lower()
            if any(c.get("email", "").lower() == email for c in STATE.contacts.values()):
                return self._send(409, {"status": "error", "category": "CONFLICT", "message": "Contact already exists."})
            cid = str(STATE.next_id)
            STATE.next_id += 1
            STATE.contacts[cid] = dict(props)
            return self._send(201, {"id": cid, "properties": props, "archived": False})

        match = re.fullmatch(r"/crm/v3/objects/contacts/(\d+)", path)
        if method == "PATCH" and match:
            cid = match.group(1)
            if cid not in STATE.contacts:
                return self._send(404, {"status": "error", "message": "Not found"})
            STATE.contacts[cid].update(body["properties"])
            return self._send(200, {"id": cid, "properties": STATE.contacts[cid], "archived": False})

        match = re.fullmatch(r"/crm/v3/lists/(\w+)/memberships/add", path)
        if method == "PUT" and match:
            members = STATE.lists.setdefault(match.group(1), [])
            added = [str(r) for r in body if str(r) not in members]
            members.extend(added)
            return self._send(200, {"recordIdsAdded": added, "recordsIdsMissing": []})

        return self._send(404, {"status": "error", "message": f"No mock for {method} {path}"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PATCH(self):
        self._route("PATCH")

    def do_PUT(self):
        self._route("PUT")


def serve(port: int = 8999) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    serve()
    print("mock HubSpot + Slack on http://127.0.0.1:8999")
    threading.Event().wait()

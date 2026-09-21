"""Every operation the Developer API documents is reachable from this SDK.

The list lives in ``sdks/operations.json``, generated from the server's OpenAPI
document and shared by all six server-side SDKs. This test calls every public method
through a recording transport — arguments are placeholders derived from each
parameter's type annotation — and checks what reached the wire covers the list.

The SDK had drifted to covering about 44 of the API's operations, with identity,
consent vault, profiles, subscriptions, assessments, discovery, AI governance,
regulatory intelligence and the reseller API absent entirely. Nothing noticed,
because nothing compared the two.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re
import typing
import unittest

from cookiemunch import CookieMunch
from cookiemunch._transport import HttpResponse

def _operations_file() -> pathlib.Path:
    """`sdks/operations.json` in the product repo; the repo root in the published SDK repo."""
    here = pathlib.Path(__file__).resolve()
    for candidate in (here.parents[2] / "operations.json", here.parents[1] / "operations.json"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("operations.json")


OPERATIONS = json.loads(_operations_file().read_text())["operations"]

PLACEHOLDER = "x1"


def _placeholder(annotation: typing.Any) -> typing.Any:
    text = str(annotation)
    # Containers first: `Mapping[str, bool]` must not be read as a bool.
    if text.startswith(("List", "list", "Sequence")):
        return [PLACEHOLDER] if "[str]" in text else [{"a": PLACEHOLDER}]
    if text.startswith(("Mapping", "Dict", "dict")):
        return {"a": PLACEHOLDER}
    if text == "bool":
        return True
    if text == "int":
        return 1
    return PLACEHOLDER


def _call_everything(client: CookieMunch) -> None:
    targets = [client] + [
        v for v in vars(client).values() if v is not None and type(v).__name__.startswith("_")
    ]
    for target in targets:
        for name, method in inspect.getmembers(target, inspect.ismethod):
            if name.startswith("_") or name in ("request",):
                continue
            args, kwargs = [], {}
            for p in inspect.signature(method).parameters.values():
                if p.default is not inspect.Parameter.empty:
                    continue
                value = _placeholder(p.annotation)
                if p.kind is inspect.Parameter.KEYWORD_ONLY:
                    kwargs[p.name] = value
                elif p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                    args.append(value)
            try:
                method(*args, **kwargs)
            except Exception:  # noqa: BLE001 — only what reached the wire matters here
                pass


class ParityTest(unittest.TestCase):
    def test_every_documented_operation_is_reachable(self) -> None:
        seen = set()

        def transport(method, url, headers, body):
            path = url.split("?", 1)[0].split("/v1", 1)[-1]
            path = "/".join("{}" if seg == PLACEHOLDER else seg for seg in path.split("/"))
            seen.add(f"{method} /v1{path}")
            return HttpResponse(status=200, headers={"Content-Type": "application/json"}, body=b"{}")

        _call_everything(CookieMunch("fck_test", base_url="https://api.example.com", transport=transport))

        missing = [op for op in OPERATIONS if op not in seen]
        self.assertEqual(missing, [], f"{len(missing)} documented operations are unreachable")
        # And nothing the API does not document — a typo'd path would otherwise 404 in use.
        self.assertEqual(sorted(seen - set(OPERATIONS)), [])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Verdandi reflex declarations and registry (VD-T1).

A reflex is declared, never improvised: trigger pattern, named action,
parameters, rate limit, owner grant. A registry file holds the
declarations; Verdandi loads and validates them at start. An undeclared
reflex does not exist and cannot fire.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class ReflexDeclarationError(ValueError):
    """Base for registry validation errors; each carries a named code."""
    code = "reflex_declaration_error"


class MalformedDeclarationError(ReflexDeclarationError):
    code = "malformed_declaration"


class DuplicateReflexError(ReflexDeclarationError):
    code = "duplicate_reflex"


class UngrantedReflexError(ReflexDeclarationError):
    code = "ungranted_reflex"


class UnknownReflexError(ReflexDeclarationError):
    code = "unknown_reflex"


@dataclass(frozen=True)
class ReflexDeclaration:
    name: str
    trigger: dict
    action: str
    params: dict = field(default_factory=dict)
    rate_limit_per_minute: int = 1
    owner_grant: str = ""
    enabled: bool = True


def _validate(raw, index):
    where = f"declaration #{index}"
    if not isinstance(raw, dict):
        raise MalformedDeclarationError(f"{where}: not an object")
    name = raw.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise MalformedDeclarationError(f"{where}: bad or missing 'name'")
    where = f"reflex '{name}'"
    trigger = raw.get("trigger")
    if not isinstance(trigger, dict) or not trigger:
        raise MalformedDeclarationError(f"{where}: 'trigger' must be a non-empty object")
    action = raw.get("action")
    if not isinstance(action, str) or not action.strip():
        raise MalformedDeclarationError(f"{where}: bad or missing 'action'")
    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise MalformedDeclarationError(f"{where}: 'params' must be an object")
    rate = raw.get("rate_limit_per_minute")
    if not isinstance(rate, int) or isinstance(rate, bool) or rate < 1:
        raise MalformedDeclarationError(f"{where}: 'rate_limit_per_minute' must be a positive integer")
    grant = raw.get("owner_grant")
    if not grant or (isinstance(grant, str) and not grant.strip()):
        raise UngrantedReflexError(f"{where}: no owner grant")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise MalformedDeclarationError(f"{where}: 'enabled' must be a boolean")
    return ReflexDeclaration(name=name, trigger=dict(trigger), action=action,
                             params=dict(params), rate_limit_per_minute=rate,
                             owner_grant=str(grant), enabled=enabled)


class ReflexRegistry:
    """Validated, immutable set of declared reflexes."""

    def __init__(self, declarations):
        self._by_name = {}
        for i, raw in enumerate(declarations):
            decl = _validate(raw, i)
            if decl.name in self._by_name:
                raise DuplicateReflexError(f"duplicate reflex '{decl.name}'")
            self._by_name[decl.name] = decl

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, dict):
            data = data.get("reflexes")
        if not isinstance(data, list):
            raise MalformedDeclarationError("registry must be a list or {'reflexes': [...]}")
        return cls(data)

    @classmethod
    def load(cls, path):
        p = Path(path)
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise MalformedDeclarationError(f"cannot load registry {p}: {e}") from e
        return cls.from_dict(data)

    def __len__(self):
        return len(self._by_name)

    def __contains__(self, name):
        return name in self._by_name

    def names(self):
        return sorted(self._by_name)

    def get(self, name):
        return self._by_name.get(name)

    def require(self, name):
        """An undeclared reflex does not exist and cannot fire."""
        decl = self._by_name.get(name)
        if decl is None:
            raise UnknownReflexError(f"undeclared reflex '{name}' does not exist")
        return decl

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from fusion_docker.models import ActionRule, ObjectProfile, normalize_token


class ObjectRegistry:
    def __init__(self, profiles: dict[str, ObjectProfile]) -> None:
        self._profiles = profiles

    @classmethod
    def from_directory(cls, path: str | Path) -> "ObjectRegistry":
        directory = Path(path)
        if not directory.exists():
            raise FileNotFoundError(f"Object directory not found: {directory}")
        if not directory.is_dir():
            raise NotADirectoryError(f"Object directory is not a directory: {directory}")

        profiles: dict[str, ObjectProfile] = {}
        for file_path in sorted(directory.iterdir()):
            if file_path.suffix.lower() not in {".yaml", ".yml"}:
                continue
            profile = _load_profile(file_path)
            profiles[profile.object_type] = profile
        if not profiles:
            raise ValueError(f"No object YAML files found in {directory}")
        return cls(profiles)

    def resolve(
        self,
        object_type: str | None = None,
        object_id: str | None = None,
    ) -> ObjectProfile | None:
        for candidate in _candidate_names(object_type, object_id):
            direct = self._profiles.get(candidate)
            if direct:
                return direct

        for candidate in _candidate_names(object_type, object_id):
            for profile in self._profiles.values():
                if profile.matches_name(candidate):
                    return profile
        return None


def _load_profile(path: Path) -> ObjectProfile:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Object YAML root must be a mapping: {path}")

    object_type = normalize_token(raw.get("object_type") or path.stem)
    template_key = normalize_token(raw.get("template_key"))
    if not template_key:
        raise ValueError(f"Object profile missing template_key: {path}")

    attributes = raw.get("attributes", {})
    if attributes is None:
        attributes = {}
    if not isinstance(attributes, dict):
        raise ValueError(f"attributes must be a mapping: {path}")

    affordances = _token_set(attributes.get("affordances", raw.get("affordances", [])))
    aliases = _token_set(raw.get("aliases", []))
    aliases.add(object_type)

    states_raw = raw.get("states", {})
    if states_raw is None:
        states_raw = {}
    if not isinstance(states_raw, dict):
        raise ValueError(f"states must be a mapping: {path}")

    default_state = normalize_token(states_raw.get("default") or "unknown")
    state_aliases = _load_state_aliases(states_raw.get("aliases", {}))
    action_rules = _load_action_rules(raw.get("action_rules", []), path=path)

    return ObjectProfile(
        object_type=object_type,
        display_name=str(raw.get("display_name", object_type)),
        template_key=template_key,
        aliases=aliases,
        attributes=attributes,
        affordances=affordances,
        default_state=default_state,
        state_aliases=state_aliases,
        action_rules=action_rules,
    )


def _load_state_aliases(raw_aliases: Any) -> dict[str, set[str]]:
    if raw_aliases is None:
        return {}
    if not isinstance(raw_aliases, dict):
        raise ValueError("states.aliases must be a mapping")

    parsed: dict[str, set[str]] = {}
    for canonical_state, aliases in raw_aliases.items():
        normalized_state = normalize_token(canonical_state)
        alias_set = _token_set(aliases)
        alias_set.add(normalized_state)
        parsed[normalized_state] = alias_set
    return parsed


def _load_action_rules(raw_rules: Any, *, path: Path) -> list[ActionRule]:
    if raw_rules is None:
        return []
    if not isinstance(raw_rules, list):
        raise ValueError(f"action_rules must be a list: {path}")

    parsed_rules: list[ActionRule] = []
    for index, rule_entry in enumerate(raw_rules):
        if not isinstance(rule_entry, dict):
            raise ValueError(f"action_rules[{index}] must be a mapping: {path}")

        when = rule_entry.get("when", {})
        if when is None:
            when = {}
        if not isinstance(when, dict):
            raise ValueError(f"action_rules[{index}].when must be a mapping: {path}")

        action = normalize_token(rule_entry.get("action"))
        if not action:
            raise ValueError(f"action_rules[{index}] missing action: {path}")

        parsed_rules.append(
            ActionRule(
                current_state=_token_set(when.get("current_state")),
                goal=_token_set(when.get("goal") or when.get("desired_state")),
                requested_action=_token_set(
                    when.get("requested_action") or when.get("input_action")
                ),
                action=action,
            )
        )
    return parsed_rules


def _candidate_names(object_type: str | None, object_id: str | None) -> Iterable[str]:
    seen: set[str] = set()
    for value in (object_type, object_id):
        token = normalize_token(value)
        if token and token not in seen:
            seen.add(token)
            yield token

        if not token:
            continue

        stripped = re.sub(r"[_-]?\d+$", "", token)
        if stripped and stripped not in seen:
            seen.add(stripped)
            yield stripped

        head = re.split(r"[_:\-]", token)[0]
        if head and head not in seen:
            seen.add(head)
            yield head


def _token_set(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        return {normalize_token(values)}
    if isinstance(values, list):
        return {
            normalize_token(str(item))
            for item in values
            if normalize_token(str(item))
        }
    raise ValueError(f"Expected string or list, got {type(values).__name__}")


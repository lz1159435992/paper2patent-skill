"""Validate the local evidence schema without a third-party runtime."""
from __future__ import annotations
import math
import re


def matches_type(value, name):
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "number": type(value) in (int, float) and math.isfinite(value),
        "boolean": type(value) is bool,
        "null": value is None,
    }.get(name, False)


def validate_record(value, schema, root=None, location=""):
    root = schema if root is None else root
    errors = []
    supported = {"$schema", "$defs", "$ref", "title", "description", "type", "required", "properties",
                 "items", "enum", "const", "anyOf", "oneOf", "allOf", "if", "then", "else",
                 "minLength", "pattern", "minimum", "minProperties", "minItems", "additionalProperties"}
    unknown = set(schema) - supported
    if unknown:
        raise ValueError("unsupported local schema constraints: " + ", ".join(sorted(unknown)))

    def add(message, path=location):
        errors.append({"path": path or "/", "message": message})

    if "$ref" in schema:
        target = root
        reference = schema["$ref"]
        if not reference.startswith("#/"):
            raise ValueError("only local schema references are supported")
        for component in reference[2:].split("/"):
            target = target[component.replace("~1", "/").replace("~0", "~")]
        return validate_record(value, target, root, location)
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(matches_type(value, name) for name in types):
            add("expected type: " + ", ".join(types))
            return errors
    if "enum" in schema and value not in schema["enum"]:
        add("value is outside the allowed enum")
    if "const" in schema and value != schema["const"]:
        add("value differs from the required constant")
    for keyword in ("anyOf", "oneOf"):
        if keyword in schema:
            count = sum(not validate_record(value, option, root, location) for option in schema[keyword])
            if (keyword == "anyOf" and not count) or (keyword == "oneOf" and count != 1):
                add("value does not satisfy " + keyword)
    for option in schema.get("allOf", []):
        errors.extend(validate_record(value, option, root, location))
    if "if" in schema:
        branch = "then" if not validate_record(value, schema["if"], root, location) else "else"
        if branch in schema:
            errors.extend(validate_record(value, schema[branch], root, location))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            add("string is too short")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            add("string does not match the required pattern")
    if type(value) in (int, float) and "minimum" in schema and value < schema["minimum"]:
        add("number is below the minimum")
    if isinstance(value, dict):
        if len(value) < schema.get("minProperties", 0):
            add("object has too few properties")
        for name in schema.get("required", []):
            if name not in value:
                add("required property is missing: " + name, location + "/" + name)
        for name, item in value.items():
            child = location + "/" + name.replace("~", "~0").replace("/", "~1")
            if name in schema.get("properties", {}):
                errors.extend(validate_record(item, schema["properties"][name], root, child))
            elif schema.get("additionalProperties") is False:
                add("unexpected property: " + name, child)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            add("array has too few items")
        for index, item in enumerate(value):
            if "items" in schema:
                errors.extend(validate_record(item, schema["items"], root, location + "/" + str(index)))
    return errors

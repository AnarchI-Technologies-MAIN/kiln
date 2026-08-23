from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import json
import re
from urllib.parse import unquote, urlparse

from engine.behavioral_fragments import fragment_identity
from engine.coal_contracts import (
    coal_failure_locations,
    coal_failure_test_ids,
    resolve_coal_contract,
)
from engine.fragment_contracts import (
    FRAGMENT_CONTRACT_VERSION,
    AssertionRecord,
    FragmentContract,
    FragmentProofLink,
    behavior_claim,
    canonical_text,
    contract_identity,
    expected_outcome,
    locate_fragment_contract,
    proof_link,
    semantic_hash,
)


PROOF_METADATA_VERSION = "KILN-PROOF-METADATA-2"
PROOF_METADATA_SCHEMA = "kiln.proof-metadata.v2"


@dataclass(frozen=True)
class ProofMetadata:
    detected_test_ids: Tuple[str, ...]
    invariant_refs: Tuple[str, ...]
    assertion_refs: Tuple[str, ...]
    behavioral_fragment_refs: Tuple[str, ...]
    assertion_records: Tuple[AssertionRecord, ...]
    fragment_contracts: Tuple[FragmentContract, ...]
    fragment_proof_links: Tuple[FragmentProofLink, ...]


def invariant_identity(
    source_path: str,
    line: int,
    assertion_text: str,
) -> str:
    material = "\0".join((
        PROOF_METADATA_VERSION,
        source_path,
        str(line),
        assertion_text,
    ))

    return (
        "KILN-INVARIANT-"
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def failure_test_ids(output: str) -> Tuple[str, ...]:
    discovered = set()

    unittest_pattern = re.compile(
        r"^(?:FAIL|ERROR):\s+([^\s(]+)(?:\s+\(([^)]+)\))?",
        re.MULTILINE,
    )

    for match in unittest_pattern.finditer(
        output
    ):
        discovered.add(
            match.group(2)
            or match.group(1)
        )

    pytest_pattern = re.compile(
        r"^(?:FAILED|ERROR)\s+([^\s]+(?:::[^\s]+)+)",
        re.MULTILINE,
    )

    for match in pytest_pattern.finditer(
        output
    ):
        discovered.add(
            match.group(1)
        )

    node_pattern = re.compile(
        r"^test at (.+?\.(?:cjs|js|jsx|mjs|ts|tsx)):(\d+):\d+\s*$",
        re.MULTILINE,
    )

    for match in node_pattern.finditer(output):
        discovered.add(
            match.group(1).replace("\\", "/")
            + ":"
            + match.group(2)
        )

    return tuple(
        sorted(discovered)
    )


def traceback_locations(
    output: str,
) -> Tuple[tuple[str, int], ...]:
    locations = set()

    unittest_pattern = re.compile(
        r'^\s*File "([^"]+\.py)", line (\d+), in ',
        re.MULTILINE,
    )

    for match in unittest_pattern.finditer(
        output
    ):
        locations.add((
            match.group(1),
            int(match.group(2)),
        ))

    pytest_pattern = re.compile(
        r"^(.+?\.py):(\d+):",
        re.MULTILINE,
    )

    for match in pytest_pattern.finditer(
        output
    ):
        locations.add((
            match.group(1),
            int(match.group(2)),
        ))

    return tuple(
        sorted(locations)
    )


def javascript_traceback_locations(
    output: str,
) -> Tuple[tuple[str, int], ...]:
    locations = set()
    pattern = re.compile(
        r"(?:\(|\s)(file:///[^\s)]+?\.(?:cjs|js|jsx|mjs|ts|tsx))"
        r":(\d+):\d+\)?",
        re.MULTILINE,
    )

    for match in pattern.finditer(output):
        locations.add((
            match.group(1),
            int(match.group(2)),
        ))

    path_pattern = re.compile(
        r"(?:\(|\s)((?:[A-Za-z]:[\\/]|/)[^\s)]+?"
        r"\.(?:cjs|js|jsx|mjs|ts|tsx)):(\d+):\d+\)?",
        re.MULTILINE,
    )

    for match in path_pattern.finditer(output):
        locations.add((
            match.group(1),
            int(match.group(2)),
        ))

    return tuple(sorted(locations))


def stable_source_location(
    specimen: Path,
    raw_path: str,
) -> tuple[Path, str] | None:
    root = Path(specimen).resolve()
    normalized_path = raw_path

    if raw_path.startswith("file://"):
        parsed = urlparse(raw_path)
        normalized_path = unquote(parsed.path)

        if re.match(
            r"^/[A-Za-z]:/",
            normalized_path,
        ):
            normalized_path = normalized_path[1:]

    path = Path(normalized_path)

    if not path.is_absolute():
        path = root / path

    try:
        resolved = path.resolve()
        relative = resolved.relative_to(
            root
        ).as_posix()
    except (OSError, ValueError):
        return None

    if not resolved.is_file():
        return None

    return resolved, relative


def enclosing_test_fragment(
    path: Path,
    relative_path: str,
    line: int,
) -> tuple[str, str, str] | None:
    located = locate_fragment_contract(
        path,
        relative_path,
        line,
        "python",
        "",
    )

    if located is None:
        return None

    contract = located.contract

    return (
        contract.test_id,
        contract.fragment_id,
        contract.role,
    )


def build_proof_metadata(
    specimen: Path,
    adapter: str,
    stdout: str,
    stderr: str,
    mutation_id: str = "",
    entry: str = "",
) -> ProofMetadata:
    output = "\n".join((
        stdout or "",
        stderr or "",
    ))
    tests = set(
        failure_test_ids(output)
    )
    invariants = set()
    assertions = set()
    fragments = set()
    assertion_records = {}
    fragment_contracts = {}
    fragment_proof_links = {}

    coal_contract = resolve_coal_contract(
        adapter,
        specimen,
    )

    if coal_contract is None:
        return ProofMetadata(
            detected_test_ids=tuple(sorted(tests)),
            invariant_refs=(),
            assertion_refs=(),
            behavioral_fragment_refs=(),
            assertion_records=(),
            fragment_contracts=(),
            fragment_proof_links=(),
        )

    tests.update(
        coal_failure_test_ids(
            coal_contract,
            output,
        )
    )

    if coal_contract.proof.parser == "python":
        locations = traceback_locations(output)
    elif coal_contract.proof.parser == "javascript":
        locations = javascript_traceback_locations(
            output
        )
    else:
        locations = coal_failure_locations(
            coal_contract,
            output,
        )

    for raw_path, line in locations:
        stable = stable_source_location(
            specimen,
            raw_path,
        )

        if stable is None:
            continue

        path, relative = stable
        relative_parts = {
            part.lower()
            for part in Path(relative).parts
        }

        if (
            coal_contract.proof.parser in {"python", "javascript"}
            and "tests" not in relative_parts
            and not Path(relative).name.lower().startswith("test_")
        ):
            continue

        located = locate_fragment_contract(
            path,
            relative,
            line,
            adapter,
            entry,
        )

        if located is None:
            continue

        fragment_contract = located.contract
        tests.add(fragment_contract.test_id)
        fragments.add(fragment_contract.fragment_id)
        invariant_id = invariant_identity(
            relative,
            fragment_contract.start_line,
            "\0".join((
                fragment_contract.test_id,
                fragment_contract.fragment_id,
                fragment_contract.expected_outcome,
            )),
        )
        invariants.add(invariant_id)
        fragment_contracts[
            fragment_contract.contract_id
        ] = fragment_contract

        if located.assertion is not None:
            assertion = located.assertion
            assertions.add(
                assertion.assertion_id
            )
            assertion_records[
                assertion.assertion_id
            ] = assertion

        link = proof_link(
            mutation_id
            or "UNBOUND-MUTATION",
            fragment_contract.fragment_id,
            fragment_contract.test_id,
            (invariant_id,),
            fragment_contract.assertion_refs,
            "TEST_FAILURE_OBSERVED",
        )
        fragment_proof_links[
            link.link_id
        ] = link

    return ProofMetadata(
        detected_test_ids=tuple(sorted(tests)),
        invariant_refs=tuple(sorted(invariants)),
        assertion_refs=tuple(sorted(assertions)),
        behavioral_fragment_refs=tuple(sorted(fragments)),
        assertion_records=tuple(
            assertion_records[key]
            for key in sorted(assertion_records)
        ),
        fragment_contracts=tuple(
            sorted(
                fragment_contracts.values(),
                key=lambda item: (
                    item.test_id,
                    item.start_line,
                    item.fragment_id,
                ),
            )
        ),
        fragment_proof_links=tuple(
            fragment_proof_links[key]
            for key in sorted(fragment_proof_links)
        ),
    )


def proof_metadata_payload(
    metadata: ProofMetadata,
) -> dict:
    return {
        "schema": PROOF_METADATA_SCHEMA,
        "proof_metadata_version": PROOF_METADATA_VERSION,
        "fragment_contract_version": FRAGMENT_CONTRACT_VERSION,
        "detected_test_ids": list(metadata.detected_test_ids),
        "invariant_refs": list(metadata.invariant_refs),
        "assertion_refs": list(metadata.assertion_refs),
        "behavioral_fragment_refs": list(
            metadata.behavioral_fragment_refs
        ),
        "assertion_records": [
            json.loads(json.dumps(asdict(item)))
            for item in metadata.assertion_records
        ],
        "fragment_contracts": [
            json.loads(json.dumps(asdict(item)))
            for item in metadata.fragment_contracts
        ],
        "fragment_proof_links": [
            json.loads(json.dumps(asdict(item)))
            for item in metadata.fragment_proof_links
        ],
    }


def canonical_string_list(
    value,
) -> bool:
    return (
        isinstance(value, list)
        and all(
            isinstance(item, str) and item
            for item in value
        )
        and value == sorted(set(value))
    )


def unique_string_list(value) -> bool:
    return (
        isinstance(value, list)
        and all(
            isinstance(item, str) and item
            for item in value
        )
        and len(value) == len(set(value))
    )


def stable_relative_path(value) -> bool:
    if not isinstance(value, str) or not value:
        return False

    path = Path(value)

    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == value
        and value != "."
    )


def content_hash(value) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value)
        is not None
    )


def validate_proof_metadata_payload(
    payload: dict,
    mutation_id: str,
) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError(
            "proof metadata evidence must be an object"
        )

    if (
        payload.get("schema")
        != PROOF_METADATA_SCHEMA
        or payload.get("proof_metadata_version")
        != PROOF_METADATA_VERSION
        or payload.get("fragment_contract_version")
        != FRAGMENT_CONTRACT_VERSION
    ):
        raise RuntimeError(
            "proof metadata evidence uses an unsupported contract"
        )

    list_fields = (
        "detected_test_ids",
        "invariant_refs",
        "assertion_refs",
        "behavioral_fragment_refs",
        "assertion_records",
        "fragment_contracts",
        "fragment_proof_links",
    )

    if any(
        not isinstance(payload.get(field), list)
        for field in list_fields
    ):
        raise RuntimeError(
            "proof metadata evidence has invalid collections"
        )

    scalar_refs = (
        "detected_test_ids",
        "invariant_refs",
        "assertion_refs",
        "behavioral_fragment_refs",
    )

    for field in scalar_refs:
        values = payload[field]

        if (
            any(not isinstance(item, str) or not item for item in values)
            or values != sorted(set(values))
        ):
            raise RuntimeError(
                "proof metadata references are not canonical: "
                + field
            )

    assertion_items = payload["assertion_records"]
    contract_items = payload["fragment_contracts"]
    link_items = payload["fragment_proof_links"]

    if (
        any(not isinstance(item, dict) for item in assertion_items)
        or any(not isinstance(item, dict) for item in contract_items)
        or any(not isinstance(item, dict) for item in link_items)
    ):
        raise RuntimeError(
            "proof metadata records must be objects"
        )

    if assertion_items != sorted(
        assertion_items,
        key=lambda item: item.get("assertion_id", ""),
    ):
        raise RuntimeError(
            "assertion records are not canonical"
        )

    if contract_items != sorted(
        contract_items,
        key=lambda item: (
            item.get("test_id", ""),
            item.get("start_line", -1),
            item.get("fragment_id", ""),
        ),
    ):
        raise RuntimeError(
            "fragment contracts are not canonical"
        )

    if link_items != sorted(
        link_items,
        key=lambda item: item.get("link_id", ""),
    ):
        raise RuntimeError(
            "fragment proof links are not canonical"
        )

    assertions = {
        item.get("assertion_id"): item
        for item in assertion_items
    }
    contracts = {
        item.get("fragment_id"): item
        for item in contract_items
    }
    link_ids = {
        item.get("link_id")
        for item in link_items
    }

    if (
        len(assertions) != len(assertion_items)
        or None in assertions
        or set(assertions) != set(payload["assertion_refs"])
    ):
        raise RuntimeError(
            "assertion records do not uniquely resolve references"
        )

    if (
        len(contracts) != len(contract_items)
        or None in contracts
        or set(contracts)
        != set(payload["behavioral_fragment_refs"])
    ):
        raise RuntimeError(
            "fragment contracts do not uniquely resolve references"
        )

    if len(link_ids) != len(link_items) or None in link_ids:
        raise RuntimeError(
            "fragment proof links are duplicate or unidentified"
        )

    tests = set(payload["detected_test_ids"])
    invariants = set(payload["invariant_refs"])

    for assertion_id, record in assertions.items():
        text = record.get("source_text")
        start = record.get("start_line")
        end = record.get("end_line")
        string_fields = (
            "assertion_id",
            "test_id",
            "source_path",
            "parent_source_hash",
            "assertion_kind",
            "source_hash",
            "source_text",
            "expected_outcome",
        )

        if (
            any(
                not isinstance(record.get(field), str)
                or not record.get(field)
                for field in string_fields
            )
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 1
            or end < start
            or not stable_relative_path(record["source_path"])
            or record["test_id"] not in tests
            or not record["test_id"].startswith(
                record["source_path"] + "::"
            )
            or not content_hash(record["parent_source_hash"])
            or not content_hash(record["source_hash"])
            or canonical_text(text) != text
            or semantic_hash(text) != record["source_hash"]
            or record["expected_outcome"] != "ASSERTION_HOLDS"
            or assertion_id != contract_identity(
                "KILN-ASSERTION-",
                record["test_id"],
                record["source_path"],
                str(start),
                str(end),
                record["source_hash"],
                record["expected_outcome"],
            )
        ):
            raise RuntimeError(
                "assertion record is invalid or transient"
            )

    linked_assertions = set()

    for fragment_id, contract in contracts.items():
        preconditions = contract.get("preconditions")
        contexts = contract.get("contexts")
        start = contract.get("start_line")
        end = contract.get("end_line")
        position = contract.get("sequence_position")
        total = contract.get("sequence_total")
        text = contract.get("source_text")
        string_fields = (
            "contract_id",
            "contract_version",
            "fragment_id",
            "test_id",
            "source_path",
            "parent_source_hash",
            "role",
            "source_hash",
            "source_text",
            "behavior_claim",
            "expected_outcome",
            "adapter",
            "reproduction_selector",
            "reproduction_scope",
            "reproduction_state",
            "compatibility_key",
        )
        reference_fields = (
            "assertion_refs",
            "required_symbols",
            "provided_symbols",
            "ambient_symbols",
            "unresolved_symbols",
            "fixture_refs",
        )
        ordered_reference_fields = (
            "precondition_fragment_refs",
            "context_fragment_refs",
        )

        if (
            any(
                not isinstance(contract.get(field), str)
                or not contract.get(field)
                for field in string_fields
            )
            or not isinstance(contract.get("entry"), str)
            or any(
                not canonical_string_list(contract.get(field))
                for field in reference_fields
            )
            or any(
                not unique_string_list(contract.get(field))
                for field in ordered_reference_fields
            )
            or not isinstance(preconditions, list)
            or not isinstance(contexts, list)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not isinstance(position, int)
            or not isinstance(total, int)
            or start < 1
            or end < start
            or position < 1
            or total < position
            or not stable_relative_path(contract["source_path"])
            or contract["test_id"] not in tests
            or not contract["test_id"].startswith(
                contract["source_path"] + "::"
            )
            or not content_hash(contract["parent_source_hash"])
            or not content_hash(contract["source_hash"])
            or canonical_text(text) != text
            or semantic_hash(text) != contract["source_hash"]
            or contract["contract_version"]
            != FRAGMENT_CONTRACT_VERSION
            or contract["role"] not in {
                "ASSERTION",
                "SETUP",
                "FIXTURE",
                "ACTION",
                "INJECTION",
                "OBSERVATION",
                "CLEANUP",
                "UNKNOWN",
            }
            or contract["behavior_claim"]
            != behavior_claim(contract["role"])
            or contract["expected_outcome"]
            != expected_outcome(contract["role"])
            or contract["reproduction_selector"]
            != contract["test_id"]
            or contract["reproduction_scope"] != "PARENT_TEST"
            or contract["reproduction_state"] != "DECLARATIVE_ONLY"
            or set(contract["assertion_refs"]) - set(assertions)
            or set(contract["ambient_symbols"])
            - set(contract["required_symbols"])
            or set(contract["unresolved_symbols"])
            - set(contract["required_symbols"])
        ):
            raise RuntimeError(
                "fragment contract is invalid or incomplete"
            )

        expected_fragment_id = fragment_identity(
            contract["test_id"],
            contract["parent_source_hash"],
            start,
            end,
            position,
            contract["role"],
            contract["source_hash"],
        )
        expected_compatibility_key = contract_identity(
            "KILN-FRAGMENT-COMPAT-",
            contract["adapter"],
            contract["role"],
            "\0".join(contract["required_symbols"]),
            "\0".join(contract["provided_symbols"]),
            "\0".join(contract["fixture_refs"]),
            contract["expected_outcome"],
        )
        expected_contract_id = contract_identity(
            "KILN-FRAGMENT-CONTRACT-",
            fragment_id,
            contract["adapter"],
            contract["entry"],
            "\0".join(contract["precondition_fragment_refs"]),
            "\0".join(contract["context_fragment_refs"]),
            "\0".join(contract["required_symbols"]),
            "\0".join(contract["provided_symbols"]),
            "\0".join(contract["fixture_refs"]),
            contract["expected_outcome"],
        )

        if (
            fragment_id != expected_fragment_id
            or contract["compatibility_key"]
            != expected_compatibility_key
            or contract["contract_id"] != expected_contract_id
        ):
            raise RuntimeError(
                "fragment contract identity is contradictory"
            )

        for records, refs, relation in (
            (
                preconditions,
                contract.get("precondition_fragment_refs"),
                "PRECONDITION",
            ),
            (
                contexts,
                contract.get("context_fragment_refs"),
                "CONTEXT",
            ),
        ):
            if (
                not isinstance(refs, list)
                or any(not isinstance(item, dict) for item in records)
                or [item.get("fragment_id") for item in records] != refs
                or len(refs) != len(set(refs))
            ):
                raise RuntimeError(
                    "fragment prerequisite references are unresolved"
                )

            for prerequisite in records:
                prerequisite_text = prerequisite.get("source_text")
                prerequisite_start = prerequisite.get("start_line")
                prerequisite_end = prerequisite.get("end_line")

                if (
                    any(
                        not isinstance(prerequisite.get(field), str)
                        or not prerequisite.get(field)
                        for field in (
                            "fragment_id",
                            "source_path",
                            "role",
                            "source_hash",
                            "source_text",
                        )
                    )
                    or not canonical_string_list(
                        prerequisite.get("required_symbols")
                    )
                    or not canonical_string_list(
                        prerequisite.get("provided_symbols")
                    )
                    or not isinstance(prerequisite_start, int)
                    or not isinstance(prerequisite_end, int)
                    or prerequisite_start < 1
                    or prerequisite_end < prerequisite_start
                    or prerequisite["source_path"]
                    != contract["source_path"]
                    or not content_hash(prerequisite["source_hash"])
                    or canonical_text(prerequisite_text)
                    != prerequisite_text
                    or semantic_hash(prerequisite_text)
                    != prerequisite["source_hash"]
                    or (
                        relation == "PRECONDITION"
                        and prerequisite_end >= start
                    )
                    or (
                        relation == "CONTEXT"
                        and not (
                            prerequisite_start <= start
                            and prerequisite_end >= end
                        )
                    )
                ):
                    raise RuntimeError(
                        "fragment prerequisite is invalid or transient"
                    )

        linked_assertions.update(contract["assertion_refs"])

        if contract["role"] == "ASSERTION":
            assertion_record = assertions.get(
                contract["assertion_refs"][0]
                if contract["assertion_refs"]
                else ""
            )

            if (
                len(contract["assertion_refs"]) != 1
                or contract["expected_outcome"] != "ASSERTION_HOLDS"
                or assertion_record is None
                or assertion_record["test_id"] != contract["test_id"]
                or assertion_record["source_path"]
                != contract["source_path"]
                or assertion_record["parent_source_hash"]
                != contract["parent_source_hash"]
                or assertion_record["start_line"] != start
                or assertion_record["end_line"] != end
                or assertion_record["source_hash"]
                != contract["source_hash"]
            ):
                raise RuntimeError(
                    "assertion fragment lacks an assertion contract"
                )
        elif contract["assertion_refs"]:
            raise RuntimeError(
                "non-assertion fragment claims assertion references"
            )

    if linked_assertions != set(assertions):
        raise RuntimeError(
            "assertion records lack fragment contracts"
        )

    linked_fragments = set()
    linked_invariants = set()

    for link in link_items:
        fragment_id = link.get("fragment_id")
        contract = contracts.get(fragment_id)

        if (
            contract is None
            or link.get("mutation_id") != mutation_id
            or link.get("test_id") != contract["test_id"]
            or not canonical_string_list(link.get("invariant_refs"))
            or not canonical_string_list(link.get("assertion_refs"))
            or link["assertion_refs"] != contract["assertion_refs"]
            or set(link["invariant_refs"]) - invariants
            or link.get("observed_outcome")
            != "TEST_FAILURE_OBSERVED"
        ):
            raise RuntimeError(
                "fragment proof link is dangling or contradictory"
            )

        expected_invariant = invariant_identity(
            contract["source_path"],
            contract["start_line"],
            "\0".join((
                contract["test_id"],
                fragment_id,
                contract["expected_outcome"],
            )),
        )
        expected_link = proof_link(
            mutation_id,
            fragment_id,
            contract["test_id"],
            tuple(link["invariant_refs"]),
            tuple(link["assertion_refs"]),
            link["observed_outcome"],
        )

        if (
            link["invariant_refs"] != [expected_invariant]
            or link.get("link_id") != expected_link.link_id
        ):
            raise RuntimeError(
                "fragment proof link identity is contradictory"
            )

        linked_fragments.add(fragment_id)
        linked_invariants.update(link["invariant_refs"])

    if (
        len(link_items) != len(contracts)
        or linked_fragments != set(contracts)
        or linked_invariants != invariants
    ):
        raise RuntimeError(
            "fragment contracts lack complete mutation proof links"
        )

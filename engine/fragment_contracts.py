from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Tuple
import ast
import builtins

from engine.behavioral_fragments import (
    classify_python_statement,
    fragment_identity,
)


FRAGMENT_CONTRACT_VERSION = "KILN-FRAGMENT-CONTRACT-1"


@dataclass(frozen=True)
class AssertionRecord:
    assertion_id: str
    test_id: str
    source_path: str
    parent_source_hash: str
    start_line: int
    end_line: int
    assertion_kind: str
    source_hash: str
    source_text: str
    expected_outcome: str


@dataclass(frozen=True)
class FragmentPrerequisite:
    fragment_id: str
    source_path: str
    start_line: int
    end_line: int
    role: str
    source_hash: str
    source_text: str
    required_symbols: Tuple[str, ...]
    provided_symbols: Tuple[str, ...]


@dataclass(frozen=True)
class FragmentContract:
    contract_id: str
    contract_version: str
    fragment_id: str
    test_id: str
    source_path: str
    parent_source_hash: str
    start_line: int
    end_line: int
    sequence_position: int
    sequence_total: int
    role: str
    source_hash: str
    source_text: str
    behavior_claim: str
    expected_outcome: str
    assertion_refs: Tuple[str, ...]
    precondition_fragment_refs: Tuple[str, ...]
    context_fragment_refs: Tuple[str, ...]
    preconditions: Tuple[FragmentPrerequisite, ...]
    contexts: Tuple[FragmentPrerequisite, ...]
    required_symbols: Tuple[str, ...]
    provided_symbols: Tuple[str, ...]
    ambient_symbols: Tuple[str, ...]
    unresolved_symbols: Tuple[str, ...]
    fixture_refs: Tuple[str, ...]
    adapter: str
    entry: str
    reproduction_selector: str
    reproduction_scope: str
    reproduction_state: str
    compatibility_key: str


@dataclass(frozen=True)
class FragmentProofLink:
    link_id: str
    mutation_id: str
    fragment_id: str
    test_id: str
    invariant_refs: Tuple[str, ...]
    assertion_refs: Tuple[str, ...]
    observed_outcome: str


@dataclass(frozen=True)
class FragmentCompatibility:
    producer_fragment_id: str
    consumer_fragment_id: str
    satisfied_symbols: Tuple[str, ...]
    missing_symbols: Tuple[str, ...]
    disposition: str


@dataclass(frozen=True)
class LocatedFragment:
    contract: FragmentContract
    assertion: AssertionRecord | None


def canonical_text(text: str) -> str:
    return text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )


def semantic_hash(text: str) -> str:
    return sha256(
        canonical_text(text).encode("utf-8")
    ).hexdigest()


def contract_identity(
    prefix: str,
    *values: str,
) -> str:
    material = "\0".join((
        FRAGMENT_CONTRACT_VERSION,
        *values,
    ))

    return (
        prefix
        + sha256(
            material.encode("utf-8")
        ).hexdigest()[:20].upper()
    )


def node_parents(tree: ast.AST):
    parents = {}

    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(
            parent
        ):
            parents[child] = parent

    return parents


def node_depth(node: ast.AST, parents) -> int:
    depth = 0
    current = node

    while current in parents:
        depth += 1
        current = parents[current]

    return depth


def enclosing_test_nodes(
    tree: ast.AST,
    line: int,
):
    candidates = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        if not node.name.startswith("test"):
            continue

        if (
            node.lineno
            <= line
            <= getattr(node, "end_lineno", node.lineno)
        ):
            candidates.append(node)

    return tuple(
        sorted(
            candidates,
            key=lambda node: (
                getattr(node, "end_lineno", node.lineno)
                - node.lineno,
                node.lineno,
                node.name,
            ),
        )
    )


def belongs_to_test(
    node: ast.AST,
    test_node: ast.AST,
    parents,
) -> bool:
    current = parents.get(node)

    while current is not None:
        if current is test_node:
            return True

        if isinstance(
            current,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return False

        current = parents.get(current)

    return False


def ordered_test_statements(
    test_node: ast.AST,
    parents,
):
    statements = tuple(
        node
        for node in ast.walk(test_node)
        if isinstance(node, ast.stmt)
        and node is not test_node
        and belongs_to_test(
            node,
            test_node,
            parents,
        )
        and not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        )
    )

    return tuple(
        sorted(
            statements,
            key=lambda node: (
                node.lineno,
                getattr(node, "col_offset", 0),
                getattr(node, "end_lineno", node.lineno),
                getattr(node, "end_col_offset", 0),
                type(node).__name__,
            ),
        )
    )


def qualified_test_id(
    test_node: ast.AST,
    relative_path: str,
    parents,
) -> str:
    names = [test_node.name]
    current = parents.get(test_node)

    while current is not None:
        if isinstance(current, ast.ClassDef):
            names.append(current.name)

        current = parents.get(current)

    return (
        relative_path
        + "::"
        + ".".join(reversed(names))
    )


def source_slice(
    source: str,
    node: ast.AST,
) -> str:
    lines = canonical_text(source).splitlines(
        keepends=True
    )

    return "".join(
        lines[
            node.lineno - 1:
            getattr(node, "end_lineno", node.lineno)
        ]
    )


def fragment_id_for_statement(
    test_id: str,
    parent_source_hash: str,
    source: str,
    node: ast.AST,
    position: int,
) -> str:
    role = classify_python_statement(node)
    text = source_slice(
        source,
        node,
    )

    return fragment_identity(
        test_id,
        parent_source_hash,
        node.lineno,
        getattr(node, "end_lineno", node.lineno),
        position,
        role,
        semantic_hash(text),
    )


def prerequisite_record(
    test_id: str,
    parent_source_hash: str,
    source: str,
    relative_path: str,
    statement: ast.AST,
    position: int,
) -> FragmentPrerequisite:
    text = source_slice(
        source,
        statement,
    )
    required, provided = statement_symbols(
        statement
    )

    return FragmentPrerequisite(
        fragment_id=fragment_id_for_statement(
            test_id,
            parent_source_hash,
            source,
            statement,
            position,
        ),
        source_path=relative_path,
        start_line=statement.lineno,
        end_line=getattr(
            statement,
            "end_lineno",
            statement.lineno,
        ),
        role=classify_python_statement(
            statement
        ),
        source_hash=semantic_hash(text),
        source_text=canonical_text(text),
        required_symbols=required,
        provided_symbols=provided,
    )

def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)

        if parent:
            return parent + "." + node.attr

        return node.attr

    return ""


def statement_symbols(
    statement: ast.AST,
) -> tuple[Tuple[str, ...], Tuple[str, ...]]:
    required = set()
    provided = set()

    for node in ast.walk(statement):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                required.add(node.id)
            elif isinstance(
                node.ctx,
                (ast.Store, ast.Del),
            ):
                provided.add(node.id)

        elif isinstance(node, ast.Attribute):
            name = dotted_name(node)

            if isinstance(node.ctx, ast.Load) and name:
                required.add(name)
            elif isinstance(
                node.ctx,
                (ast.Store, ast.Del),
            ) and name:
                provided.add(name)

    return (
        tuple(sorted(required)),
        tuple(sorted(provided)),
    )


def ambient_symbols(
    tree: ast.AST,
) -> Tuple[str, ...]:
    symbols = set(dir(builtins))

    for node in getattr(tree, "body", ()):  # module scope only
        if isinstance(node, ast.Import):
            for alias in node.names:
                symbols.add(
                    alias.asname
                    or alias.name.split(".")[0]
                )

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                symbols.add(
                    alias.asname
                    or alias.name
                )

        elif isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            symbols.add(node.name)

        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            _, provided = statement_symbols(node)
            symbols.update(provided)

    return tuple(sorted(symbols))


def fixture_refs(
    test_node: ast.AST,
    parents,
) -> Tuple[str, ...]:
    refs = set()

    for argument in (
        *test_node.args.posonlyargs,
        *test_node.args.args,
        *test_node.args.kwonlyargs,
    ):
        if argument.arg not in {"self", "cls"}:
            refs.add("ARGUMENT:" + argument.arg)

    parent = parents.get(test_node)

    while parent is not None:
        if isinstance(parent, ast.ClassDef):
            for item in parent.body:
                if isinstance(
                    item,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ) and item.name in {
                    "setUp",
                    "setUpClass",
                    "tearDown",
                    "tearDownClass",
                }:
                    refs.add(
                        "UNITTEST:"
                        + parent.name
                        + "."
                        + item.name
                    )

        parent = parents.get(parent)

    return tuple(sorted(refs))


def assertion_kind(statement: ast.AST) -> str:
    if isinstance(statement, ast.Assert):
        return "PYTHON_ASSERT"

    if isinstance(statement, ast.With):
        return "ASSERTION_CONTEXT"

    return "ASSERTION_CALL"


def expected_outcome(role: str) -> str:
    if role == "ASSERTION":
        return "ASSERTION_HOLDS"

    if role == "CLEANUP":
        return "CLEANUP_COMPLETES"

    return "COMPLETES_WITHOUT_EXCEPTION"


def behavior_claim(role: str) -> str:
    claims = {
        "ASSERTION": "declared assertion holds",
        "SETUP": "test state is prepared",
        "FIXTURE": "fixture state is established",
        "ACTION": "test action completes",
        "INJECTION": "test injection completes",
        "OBSERVATION": "test observation completes",
        "CLEANUP": "test cleanup completes",
        "UNKNOWN": "statement completes under parent test contract",
    }

    return claims[role]


def locate_fragment_contract(
    path: Path,
    relative_path: str,
    line: int,
    adapter: str,
    entry: str,
) -> LocatedFragment | None:
    source = Path(path).read_text(
        encoding="utf-8"
    )
    tree = ast.parse(
        source,
        filename=str(path),
    )
    parents = node_parents(tree)
    tests = enclosing_test_nodes(
        tree,
        line,
    )

    if not tests:
        return None

    test_node = tests[0]
    statements = ordered_test_statements(
        test_node,
        parents,
    )
    containing = tuple(
        statement
        for statement in statements
        if statement.lineno
        <= line
        <= getattr(statement, "end_lineno", statement.lineno)
    )

    if not containing:
        return None

    statement = min(
        containing,
        key=lambda node: (
            getattr(node, "end_lineno", node.lineno)
            - node.lineno,
            -node_depth(node, parents),
            getattr(node, "col_offset", 0),
            type(node).__name__,
        ),
    )
    position = statements.index(statement) + 1
    test_id = qualified_test_id(
        test_node,
        relative_path,
        parents,
    )
    normalized_source = canonical_text(source)
    parent_hash = semantic_hash(
        normalized_source
    )
    text = source_slice(
        normalized_source,
        statement,
    )
    role = classify_python_statement(
        statement
    )
    fragment_id = fragment_id_for_statement(
        test_id,
        parent_hash,
        normalized_source,
        statement,
        position,
    )
    preceding = tuple(
        item
        for item in statements
        if getattr(item, "end_lineno", item.lineno)
        < statement.lineno
    )
    contexts = tuple(
        item
        for item in containing
        if item is not statement
    )
    precondition_refs = tuple(
        fragment_id_for_statement(
            test_id,
            parent_hash,
            normalized_source,
            item,
            statements.index(item) + 1,
        )
        for item in preceding
    )
    context_refs = tuple(
        fragment_id_for_statement(
            test_id,
            parent_hash,
            normalized_source,
            item,
            statements.index(item) + 1,
        )
        for item in contexts
    )
    precondition_records = tuple(
        prerequisite_record(
            test_id,
            parent_hash,
            normalized_source,
            relative_path,
            item,
            statements.index(item) + 1,
        )
        for item in preceding
    )
    context_records = tuple(
        prerequisite_record(
            test_id,
            parent_hash,
            normalized_source,
            relative_path,
            item,
            statements.index(item) + 1,
        )
        for item in contexts
    )
    required, provided = statement_symbols(
        statement
    )
    available_ambient = set(
        ambient_symbols(tree)
    )
    ambient = tuple(
        sorted(
            item
            for item in required
            if item.split(".", 1)[0]
            in available_ambient
        )
    )
    supplied = set(
        available_ambient
    )

    for item in preceding:
        _, item_provided = statement_symbols(
            item
        )
        supplied.update(item_provided)

    fixtures = fixture_refs(
        test_node,
        parents,
    )
    supplied.update(
        item.split(":", 1)[-1]
        for item in fixtures
    )
    supplied.update({"self", "cls"})
    unresolved = tuple(
        sorted(
            item
            for item in required
            if item.split(".", 1)[0]
            not in supplied
        )
    )
    assertion = None
    assertion_refs = ()
    outcome = expected_outcome(role)

    if role == "ASSERTION":
        assertion_id = contract_identity(
            "KILN-ASSERTION-",
            test_id,
            relative_path,
            str(statement.lineno),
            str(getattr(statement, "end_lineno", statement.lineno)),
            semantic_hash(text),
            outcome,
        )
        assertion = AssertionRecord(
            assertion_id=assertion_id,
            test_id=test_id,
            source_path=relative_path,
            parent_source_hash=parent_hash,
            start_line=statement.lineno,
            end_line=getattr(
                statement,
                "end_lineno",
                statement.lineno,
            ),
            assertion_kind=assertion_kind(
                statement
            ),
            source_hash=semantic_hash(text),
            source_text=canonical_text(text),
            expected_outcome=outcome,
        )
        assertion_refs = (
            assertion.assertion_id,
        )

    compatibility_key = contract_identity(
        "KILN-FRAGMENT-COMPAT-",
        adapter,
        role,
        "\0".join(required),
        "\0".join(provided),
        "\0".join(fixtures),
        outcome,
    )
    contract_id = contract_identity(
        "KILN-FRAGMENT-CONTRACT-",
        fragment_id,
        adapter,
        entry,
        "\0".join(precondition_refs),
        "\0".join(context_refs),
        "\0".join(required),
        "\0".join(provided),
        "\0".join(fixtures),
        outcome,
    )
    contract = FragmentContract(
        contract_id=contract_id,
        contract_version=FRAGMENT_CONTRACT_VERSION,
        fragment_id=fragment_id,
        test_id=test_id,
        source_path=relative_path,
        parent_source_hash=parent_hash,
        start_line=statement.lineno,
        end_line=getattr(
            statement,
            "end_lineno",
            statement.lineno,
        ),
        sequence_position=position,
        sequence_total=len(statements),
        role=role,
        source_hash=semantic_hash(text),
        source_text=canonical_text(text),
        behavior_claim=behavior_claim(role),
        expected_outcome=outcome,
        assertion_refs=assertion_refs,
        precondition_fragment_refs=precondition_refs,
        context_fragment_refs=context_refs,
        preconditions=precondition_records,
        contexts=context_records,
        required_symbols=required,
        provided_symbols=provided,
        ambient_symbols=ambient,
        unresolved_symbols=unresolved,
        fixture_refs=fixtures,
        adapter=adapter,
        entry=entry,
        reproduction_selector=test_id,
        reproduction_scope="PARENT_TEST",
        reproduction_state="DECLARATIVE_ONLY",
        compatibility_key=compatibility_key,
    )

    return LocatedFragment(
        contract=contract,
        assertion=assertion,
    )


def proof_link(
    mutation_id: str,
    fragment_id: str,
    test_id: str,
    invariant_refs: Tuple[str, ...],
    assertion_refs: Tuple[str, ...],
    observed_outcome: str,
) -> FragmentProofLink:
    link_id = contract_identity(
        "KILN-FRAGMENT-PROOF-",
        mutation_id,
        fragment_id,
        test_id,
        "\0".join(invariant_refs),
        "\0".join(assertion_refs),
        observed_outcome,
    )

    return FragmentProofLink(
        link_id=link_id,
        mutation_id=mutation_id,
        fragment_id=fragment_id,
        test_id=test_id,
        invariant_refs=invariant_refs,
        assertion_refs=assertion_refs,
        observed_outcome=observed_outcome,
    )


def compare_fragment_contracts(
    producer: FragmentContract,
    consumer: FragmentContract,
) -> FragmentCompatibility:
    if producer.adapter != consumer.adapter:
        return FragmentCompatibility(
            producer_fragment_id=producer.fragment_id,
            consumer_fragment_id=consumer.fragment_id,
            satisfied_symbols=(),
            missing_symbols=consumer.required_symbols,
            disposition="ADAPTER_MISMATCH",
        )

    available = set(producer.provided_symbols)
    available.update(consumer.ambient_symbols)
    available.update({"self", "cls"})

    for fixture in consumer.fixture_refs:
        available.add(
            fixture.split(":", 1)[-1]
        )

    for prerequisite in (
        *consumer.preconditions,
        *consumer.contexts,
    ):
        available.update(
            prerequisite.provided_symbols
        )

    available_roots = {
        item.split(".", 1)[0]
        for item in available
    }
    required = set(consumer.required_symbols)
    satisfied = tuple(
        sorted(
            item
            for item in required
            if item in available
            or item.split(".", 1)[0]
            in available_roots
        )
    )
    missing = tuple(
        sorted(required - set(satisfied))
    )
    disposition = (
        "STATICALLY_COMPATIBLE"
        if not missing
        else "REQUIRES_PRECONDITIONS"
    )

    return FragmentCompatibility(
        producer_fragment_id=producer.fragment_id,
        consumer_fragment_id=consumer.fragment_id,
        satisfied_symbols=satisfied,
        missing_symbols=missing,
        disposition=disposition,
    )

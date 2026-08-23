from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from engine.coal_contracts import CoalMutationRule, CoalProof
from engine.coal_tongs import CoalPack, coal_pack, discover_coal_packs
from engine.coal_venvs import CoalVenvAdapter, coal_venv_adapter


@dataclass(frozen=True)
class LanguageAdapter:
    adapter: str
    languages: Tuple[str, ...]
    source_extensions: Tuple[str, ...]
    mutation_strategy: str
    mutation_rules: Tuple[CoalMutationRule, ...]


@dataclass(frozen=True)
class BuildAdapter:
    adapter: str
    build_systems: Tuple[str, ...]
    rebuild_commands: Tuple[Tuple[str, ...], ...]


@dataclass(frozen=True)
class TestRunnerAdapter:
    adapter: str
    test_runners: Tuple[str, ...]
    test_command: Tuple[str, ...]
    proof: CoalProof


@dataclass(frozen=True)
class CoalAdapterBundle:
    adapter: str
    language: LanguageAdapter
    build: BuildAdapter
    test: TestRunnerAdapter
    venv: CoalVenvAdapter


def adapter_bundle(pack: CoalPack) -> CoalAdapterBundle:
    contract = pack.contract
    return CoalAdapterBundle(
        adapter=pack.adapter,
        language=LanguageAdapter(
            adapter=pack.adapter,
            languages=contract.languages,
            source_extensions=contract.source_extensions,
            mutation_strategy=contract.mutation_strategy,
            mutation_rules=contract.mutation_rules,
        ),
        build=BuildAdapter(
            adapter=pack.adapter,
            build_systems=pack.build_systems,
            rebuild_commands=contract.execution.rebuild_commands,
        ),
        test=TestRunnerAdapter(
            adapter=pack.adapter,
            test_runners=pack.test_runners,
            test_command=contract.execution.test_command,
            proof=contract.proof,
        ),
        venv=coal_venv_adapter(pack.venv_adapter),
    )


def discover_adapter_bundles(root: Path | None = None) -> Tuple[CoalAdapterBundle, ...]:
    return tuple(adapter_bundle(pack) for pack in discover_coal_packs(root))


def coal_adapter_bundle(adapter: str, root: Path | None = None) -> CoalAdapterBundle:
    return adapter_bundle(coal_pack(adapter, root))

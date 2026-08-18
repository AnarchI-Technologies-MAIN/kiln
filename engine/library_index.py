from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple
import csv


@dataclass(frozen=True)
class KilnLibraryRecord:
    """Kiln-scoped view of one shared Test Library occurrence.

    Kiln does not own the underlying test record.
    The stable Test Library identifiers remain authoritative.
    """

    occurrence_id: str
    content_id: str
    repository_root: str
    repository_path: str
    absolute_path: str
    language: str = ""
    runner: str = ""
    execution_safety: str = ""
    execution_context_id: str = ""
    taxonomy: Tuple[str, ...] = field(default_factory=tuple)


class KilnLibraryIndex:
    """Read-only Kiln index over the shared AnarchI Test Library."""

    CONTENT_FILE = "test-content-registry-001.csv"
    OCCURRENCE_FILE = "test-occurrence-registry-001.csv"
    TAXONOMY_FILE = "test-taxonomy-relations-001.csv"
    RUNNER_FILE = "test-runner-topology-001.csv"
    SAFETY_FILE = "test-execution-safety-001.csv"
    CONTEXT_FILE = "test-execution-context-index-001.csv"

    def __init__(self, library_root: Path | str) -> None:
        self.library_root = Path(library_root).resolve()
        self.registry_root = self.library_root / "registry"
        self._records: Dict[str, KilnLibraryRecord] = {}

    @staticmethod
    def _read_csv(path: Path) -> List[dict]:
        if not path.exists():
            return []

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _first(row: Mapping[str, str], *names: str) -> str:
        for name in names:
            value = row.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def load(self) -> "KilnLibraryIndex":
        """Build the Kiln view without modifying Test Library data."""

        occurrences = self._read_csv(self.registry_root / self.OCCURRENCE_FILE)
        taxonomy_rows = self._read_csv(self.registry_root / self.TAXONOMY_FILE)
        runner_rows = self._read_csv(self.registry_root / self.RUNNER_FILE)
        safety_rows = self._read_csv(self.registry_root / self.SAFETY_FILE)
        context_rows = self._read_csv(self.registry_root / self.CONTEXT_FILE)

        taxonomy_by_occurrence: Dict[str, List[str]] = {}

        for row in taxonomy_rows:
            occurrence_id = self._first(
                row,
                "occurrence_id",
                "test_occurrence_id",
            )

            relation = self._first(
                row,
                "taxonomy_value",
                "value",
                "taxonomy",
                "relation",
                "name",
            )

            if occurrence_id and relation:
                taxonomy_by_occurrence.setdefault(occurrence_id, []).append(relation)

        runner_by_occurrence: Dict[str, dict] = {}

        for row in runner_rows:
            occurrence_id = self._first(
                row,
                "occurrence_id",
                "test_occurrence_id",
            )

            if occurrence_id:
                runner_by_occurrence[occurrence_id] = row

        safety_by_occurrence: Dict[str, dict] = {}

        for row in safety_rows:
            occurrence_id = self._first(
                row,
                "occurrence_id",
                "test_occurrence_id",
            )

            if occurrence_id:
                safety_by_occurrence[occurrence_id] = row

        context_by_occurrence: Dict[str, dict] = {}

        for row in context_rows:
            occurrence_id = self._first(
                row,
                "occurrence_id",
                "test_occurrence_id",
            )

            if occurrence_id:
                context_by_occurrence[occurrence_id] = row

        records: Dict[str, KilnLibraryRecord] = {}

        for row in occurrences:
            occurrence_id = self._first(
                row,
                "occurrence_id",
                "test_occurrence_id",
                "id",
            )

            if not occurrence_id:
                continue

            content_id = self._first(
                row,
                "content_id",
                "test_content_id",
                "content_identity",
            )

            runner_row = runner_by_occurrence.get(occurrence_id, {})
            safety_row = safety_by_occurrence.get(occurrence_id, {})
            context_row = context_by_occurrence.get(occurrence_id, {})

            records[occurrence_id] = KilnLibraryRecord(
                occurrence_id=occurrence_id,
                content_id=content_id,
                repository_root=self._first(
                    row,
                    "repository_root",
                    "repository",
                    "repo_root",
                ),
                repository_path=self._first(
                    row,
                    "repository_path",
                    "relative_path",
                    "path",
                ),
                absolute_path=self._first(
                    row,
                    "absolute_path",
                    "source_path",
                ),
                language=self._first(row, "language"),
                runner=self._first(
                    runner_row,
                    "runner",
                    "runner_type",
                    "resolved_runner",
                ),
                execution_safety=self._first(
                    safety_row,
                    "execution_safety",
                    "safety",
                    "safety_class",
                    "disposition",
                ),
                execution_context_id=self._first(
                    context_row,
                    "execution_context_id",
                    "context_id",
                ),
                taxonomy=tuple(
                    sorted(set(taxonomy_by_occurrence.get(occurrence_id, [])))
                ),
            )

        self._records = records
        return self

    def get(self, occurrence_id: str) -> Optional[KilnLibraryRecord]:
        return self._records.get(occurrence_id)

    def all(self) -> Tuple[KilnLibraryRecord, ...]:
        return tuple(
            self._records[key]
            for key in sorted(self._records)
        )

    def eligible(
        self,
        *,
        runners: Optional[Iterable[str]] = None,
        require_taxonomy: Optional[Iterable[str]] = None,
    ) -> Tuple[KilnLibraryRecord, ...]:
        runner_filter = set(runners or [])
        taxonomy_filter = set(require_taxonomy or [])
        selected: List[KilnLibraryRecord] = []

        for record in self.all():
            if runner_filter and record.runner not in runner_filter:
                continue

            record_taxonomy = set(record.taxonomy)

            if taxonomy_filter and not taxonomy_filter.issubset(record_taxonomy):
                continue

            selected.append(record)

        return tuple(selected)

    def __len__(self) -> int:
        return len(self._records)

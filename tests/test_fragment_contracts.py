import tempfile
import unittest
from pathlib import Path

from engine.fragment_contracts import (
    compare_fragment_contracts,
    locate_fragment_contract,
)


SOURCE = (
    "import tempfile\n"
    "import unittest\n"
    "\n"
    "class ContractTests(unittest.TestCase):\n"
    "    def setUp(self):\n"
    "        self.seed = 3\n"
    "\n"
    "    def test_nested_assertion(self):\n"
    "        value = self.seed\n"
    "        with tempfile.TemporaryDirectory() as workspace:\n"
    "            observed = workspace and value\n"
    "            with self.assertRaises(ValueError):\n"
    "                raise TypeError(observed)\n"
)


class FragmentContractTests(unittest.TestCase):

    def locate(self, root: Path, newline: str = "\n"):
        tests = root / "tests"
        tests.mkdir()
        path = tests / "test_contract.py"
        path.write_text(
            SOURCE.replace("\n", newline),
            encoding="utf-8",
            newline="",
        )

        return locate_fragment_contract(
            path,
            "tests/test_contract.py",
            12,
            "python",
            "tests",
        )

    def test_nested_assertion_retains_setup_context_and_reproduction(self):
        with tempfile.TemporaryDirectory() as temp:
            located = self.locate(Path(temp))
            contract = located.contract

            self.assertEqual(contract.role, "ASSERTION")
            self.assertIsNotNone(located.assertion)
            self.assertEqual(
                contract.assertion_refs,
                (located.assertion.assertion_id,),
            )
            self.assertEqual(
                contract.reproduction_selector,
                "tests/test_contract.py::ContractTests.test_nested_assertion",
            )
            self.assertEqual(contract.reproduction_scope, "PARENT_TEST")
            self.assertEqual(
                contract.reproduction_state,
                "DECLARATIVE_ONLY",
            )
            self.assertTrue(contract.precondition_fragment_refs)
            self.assertEqual(len(contract.context_fragment_refs), 1)
            self.assertIn("observed", contract.required_symbols)
            self.assertFalse(contract.unresolved_symbols)

    def test_contract_identity_is_root_and_newline_independent(self):
        with tempfile.TemporaryDirectory() as first_temp:
            with tempfile.TemporaryDirectory() as second_temp:
                first = self.locate(Path(first_temp), "\n").contract
                second = self.locate(Path(second_temp), "\r\n").contract

        self.assertEqual(first, second)
        self.assertNotIn(first_temp, repr(first))
        self.assertNotIn(second_temp, repr(second))

    def test_compatibility_accounts_for_declared_prerequisites(self):
        with tempfile.TemporaryDirectory() as temp:
            contract = self.locate(Path(temp)).contract

        compatibility = compare_fragment_contracts(
            contract,
            contract,
        )

        self.assertEqual(
            compatibility.disposition,
            "STATICALLY_COMPATIBLE",
        )
        self.assertFalse(compatibility.missing_symbols)


if __name__ == "__main__":
    unittest.main()

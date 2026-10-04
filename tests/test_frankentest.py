import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from engine.cli import main
from engine.cycle_orchestrator import run_cycle
from engine.frankentest import approve_frankentest, compose_source, digest, execute_candidate, frankentest, proven_segments, read_json
from engine.coal_contracts import resolve_coal_contract
from tests.test_coal_contracts import coal_payload


class FrankentestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.repo = cls.root / 'target'
        cls.repo.mkdir()
        (cls.repo / 'tests').mkdir()
        (cls.repo / 'app.py').write_text('def enabled():\n    return True\n\ndef closed():\n    return False\n', encoding='utf-8')
        (cls.repo / 'tests/test_app.py').write_text('import unittest\nfrom app import enabled, closed\n\nclass AppTests(unittest.TestCase):\n    def test_enabled(self):\n        self.assertTrue(enabled())\n\n    def test_closed(self):\n        self.assertFalse(closed())\n', encoding='utf-8')
        for args in (['init', '-q'], ['config', 'user.name', 'Kiln Fixture'], ['config', 'user.email', 'fixture@example.invalid'], ['add', '.'], ['commit', '-qm', 'fixture']):
            subprocess.run(['git', '-C', str(cls.repo)] + args, check=True, capture_output=True)
        cls.previous_inbox = os.environ.get('KILN_ADJUDICATION_INBOX')
        os.environ['KILN_ADJUDICATION_INBOX'] = str(cls.root / 'inbox')
        result = run_cycle(str(cls.repo), 'python', 'tests', 2, 'stable', cls.root / 'cycles')
        if not result.baseline_passed or result.fractures_observed != 2:
            raise RuntimeError('Fixture must supply two executed, proven assertion fractures')
        cls.evidence = Path(result.proof_metadata_path)
        cls.aggregate = read_json(cls.evidence)
        cls.segments = proven_segments(cls.repo, cls.aggregate)

    @classmethod
    def tearDownClass(cls):
        if cls.previous_inbox is None:
            os.environ.pop('KILN_ADJUDICATION_INBOX', None)
        else:
            os.environ['KILN_ADJUDICATION_INBOX'] = cls.previous_inbox
        cls.temp.cleanup()

    def test_real_fractures_generate_recursively_qualified_candidate(self):
        result = frankentest(self.repo, self.evidence, self.root / 'qualified', adapter='python', max_candidates=1)
        self.assertEqual(result['disposition'], 'QUALIFIED_APPROVAL_CANDIDATES')
        self.assertTrue(result['original_preserved'])
        self.assertFalse(result['system_wide_approved'])
        candidate = result['candidates'][0]
        self.assertEqual(len(candidate['qualification']), 10)
        self.assertEqual(sum(q['kind'] == 'assertion_removal_control' for q in candidate['qualification']), 4)
        self.assertTrue(all(q['specimen_removed'] for q in candidate['qualification']))

    def test_explicit_approval_requalifies_before_registry_admission(self):
        result = frankentest(self.repo, self.evidence, self.root / 'approval-source', adapter='python', max_candidates=1)
        candidate = result['candidates'][0]
        path = self.root / 'approval-source' / candidate['candidate_id'] / 'candidate.json'
        receipt = approve_frankentest(self.repo, path, self.evidence, digest(path.read_bytes()), 'unit-test-authority', self.root / 'registry')
        self.assertEqual(receipt['disposition'], 'APPROVED_SYSTEM_WIDE_TEST_CANDIDATE')
        self.assertFalse(receipt['installed_into_library'])
        self.assertTrue(Path(receipt['requalification_report']).is_file())
        with self.assertRaisesRegex(RuntimeError, 'APPROVAL_CANDIDATE_PIN'):
            approve_frankentest(self.repo, path, self.evidence, '0' * 64, 'unit-test-authority', self.root / 'bad-registry')

    def test_import_errors_are_not_assertion_fractures(self):
        repository = self.root / 'broken-execution'
        repository.mkdir()
        execution = execute_candidate(repository, 'candidate.py', 'import module_that_does_not_exist\n', resolve_coal_contract('python', self.repo), 5, False)
        self.assertEqual(execution['classification'], 'EXECUTION_FAILED')

    def test_skipped_tests_are_not_qualification(self):
        repository = self.root / 'skipped-execution'
        repository.mkdir()
        code = "print('KILN_FRANKENTEST_RESULT={\"tests\":1,\"failures\":0,\"errors\":0,\"skipped\":1,\"expected_failures\":0,\"unexpected_successes\":0}')\n"
        execution = execute_candidate(repository, 'candidate.py', code, resolve_coal_contract('python', self.repo), 5, False)
        self.assertEqual(execution['classification'], 'EXECUTION_FAILED')

    def test_zero_tests_are_not_qualification(self):
        repository = self.root / 'empty-execution'
        repository.mkdir()
        code = "print('KILN_FRANKENTEST_RESULT={\"tests\":0,\"failures\":0,\"errors\":0,\"skipped\":0,\"expected_failures\":0,\"unexpected_successes\":0}')\n"
        execution = execute_candidate(repository, 'candidate.py', code, resolve_coal_contract('python', self.repo), 5, False)
        self.assertEqual(execution['classification'], 'EXECUTION_FAILED')

    def test_auto_without_declaration_is_held(self):
        with self.assertRaisesRegex(RuntimeError, 'DECLARED_ENVIRONMENT_MISSING'):
            frankentest(self.repo, self.evidence, self.root / 'missing-profile')

    def test_auto_declared_environment_qualifies_generic_python_segments(self):
        repository = self.root / 'declared-target'
        subprocess.run(['git', 'clone', '-q', str(self.repo), str(repository)], check=True, capture_output=True)
        payload = coal_payload('python')
        payload.update(adapter='python-declared', languages=['python'], sourceExtensions=['.py'])
        payload['mutation']['rules'] = [{'kind':'PYTHON_BOOLEAN_REPLACEMENT','pattern':r'\bFalse\b|\bTrue\b','replacements':{'False':'True','True':'False'},'ignoreCase':False}]
        payload['execution'].update(rebuildCommands=[], testCommand=['python','-B','-m','unittest','discover','-s','tests'], entryKind='none', appendEntry=False)
        payload['proof'].update(locationPatterns=[r'File "(?P<path>[^"\r\n]+\.py)", line (?P<line>\d+)'], testPatterns=[r'^FAIL: (?P<test>[^\r\n]+)$'], assertionPatterns=[r'\bself\.assert\w+\s*\('])
        (repository/'kiln.coal.json').write_text(json.dumps(payload), encoding='utf-8')
        subprocess.run(['git','-C',str(repository),'add','.'], check=True, capture_output=True)
        subprocess.run(['git','-C',str(repository),'-c','user.name=Kiln Fixture','-c','user.email=fixture@example.invalid','commit','-qm','declared profile'], check=True, capture_output=True)
        cycle = run_cycle(str(repository), 'auto', '', 2, 'stable', self.root/'declared-cycles')
        self.assertEqual(cycle.fractures_observed, 2)
        result = frankentest(repository, Path(cycle.proof_metadata_path), self.root/'declared-frankentest', max_candidates=1)
        self.assertEqual(result['disposition'], 'QUALIFIED_APPROVAL_CANDIDATES', result)

    def test_cleanup_failure_holds_candidate(self):
        from engine.sandbox_execution import SandboxExecutor
        real_release = SandboxExecutor.release
        def released_but_unverified(executor, lease):
            real_release(executor, lease)
            return False
        with patch.object(SandboxExecutor, 'release', released_but_unverified):
            result = frankentest(self.repo, self.evidence, self.root/'cleanup-failed', adapter='python', max_candidates=1)
        self.assertEqual(result['disposition'], 'HELD')
        self.assertEqual(result['candidates'][0]['disposition'], 'QUALIFICATION_FAILED')

    def test_metadata_tampering_is_rejected(self):
        altered = copy.deepcopy(self.aggregate)
        altered['trials'][0]['metadata']['fragment_contracts'][0]['source_text'] = 'self.assertTrue(True)'
        with self.assertRaises(RuntimeError):
            proven_segments(self.repo, altered)

    def test_duplicate_proof_trial_is_rejected(self):
        altered = copy.deepcopy(self.aggregate)
        altered['trials'].append(copy.deepcopy(altered['trials'][0]))
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_PROOF_TRIAL'):
            proven_segments(self.repo, altered)

    def test_duplicate_segment_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_SEGMENT'):
            compose_source(self.repo, [self.segments[0], self.segments[0]])

    def test_cross_module_context_is_held(self):
        altered = copy.deepcopy(self.segments)
        altered[0]['contract']['source_path'] = 'tests/another.py'
        with self.assertRaisesRegex(RuntimeError, 'CROSS_MODULE_CONTEXT_UNRESOLVED'):
            compose_source(self.repo, altered)

    def test_missing_symbols_are_held(self):
        altered = copy.deepcopy(self.aggregate)
        altered['trials'][0]['metadata']['fragment_contracts'][0]['unresolved_symbols'] = ['unknown']
        with self.assertRaises(RuntimeError):
            proven_segments(self.repo, altered)

    def test_output_under_target_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'OUTPUT_MUST_BE_OUTSIDE_TARGET'):
            frankentest(self.repo, self.evidence, self.repo / 'generated')

    def test_unbounded_budget_is_rejected(self):
        for budget in (0, 65, True):
            with self.assertRaisesRegex(RuntimeError, 'CANDIDATE_BUDGET'):
                frankentest(self.repo, self.evidence, self.root / 'bad', max_candidates=budget)

    def test_unbounded_deadline_is_rejected(self):
        for timeout in (0, 301, float('nan'), float('inf')):
            with self.assertRaisesRegex(RuntimeError, 'TIME_BUDGET'):
                frankentest(self.repo, self.evidence, self.root / 'bad', timeout=timeout)

    def test_duplicate_json_keys_are_rejected(self):
        path = self.root / 'duplicate.json'
        path.write_text('{"trials": [], "trials": []}', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_JSON_KEY'):
            read_json(path)

    def test_cli_requires_destructive_authorization(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = main(['frankentest', str(self.repo), '--evidence', str(self.evidence), '--output', str(self.root / 'cli'), '--json'])
        self.assertEqual(result, 5)
        self.assertIn('DESTRUCTIVE_AUTHORIZATION_REQUIRED', output.getvalue())


if __name__ == '__main__':
    unittest.main()

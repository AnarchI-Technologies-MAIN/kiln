"""Source-bound composition and recursive qualification of test candidates.

The first executable backend is Python unittest. Other languages remain
explicitly unsupported rather than being relabeled as Python. Approval and
shared-library installation are separate from qualification.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from engine.coal_contracts import resolve_coal_contract
from engine.isolation_boundary import repository_path_is_absolute, sanitize_environment
from engine.mutation_adapters import discover_mutations, expand_contract_command
from engine.mutation_executor import apply_mutation
from engine.proof_metadata import validate_proof_metadata_payload
from engine.sandbox_execution import SandboxExecutor
from engine.target_intake import inspect_target

SCHEMA = 'kiln.frankentest-candidate.v1'
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def normalized(raw):
    return raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')


def contained(root, name):
    root = Path(root).resolve()
    require(isinstance(name, str) and name and '\\' not in name, 'NONCANONICAL_PATH')
    relative = Path(name)
    require(not repository_path_is_absolute(name) and '..' not in relative.parts, 'PATH_ESCAPE')
    path = (root / relative).resolve()
    require(path.is_relative_to(root), 'PATH_ESCAPE')
    return path


def read_json(path, raw=None):
    require(path.stat().st_size <= MAX_EVIDENCE_BYTES, 'EVIDENCE_BUDGET')
    raw = path.read_bytes() if raw is None else raw
    require(len(raw) <= MAX_EVIDENCE_BYTES, 'EVIDENCE_BUDGET')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def proven_segments(root, aggregate):
    require(isinstance(aggregate, dict), 'PROOF_AGGREGATE_SCHEMA')
    require(aggregate.get('schema') == 'kiln.proof-metadata-aggregate.v1', 'PROOF_AGGREGATE_SCHEMA')
    require(aggregate.get('proof_evidence_version') == 'KILN-PROOF-EVIDENCE-3', 'PROOF_AGGREGATE_VERSION')
    trials = aggregate.get('trials')
    require(isinstance(trials, list) and len(trials) <= 4096, 'PROOF_TRIAL_BUDGET')
    segments = []
    seen_trials = set()
    for trial in trials:
        require(isinstance(trial, dict) and 'mutation_id' in trial and 'metadata' in trial, 'PROOF_TRIAL_SCHEMA')
        mutation_id = trial['mutation_id']
        require(mutation_id not in seen_trials, 'DUPLICATE_PROOF_TRIAL')
        seen_trials.add(mutation_id)
        payload = trial['metadata']
        validate_proof_metadata_payload(payload, mutation_id)
        for contract in payload['fragment_contracts']:
            if contract['role'] != 'ASSERTION':
                continue
            require(contract['adapter'] in ('python', 'auto') or contract['source_path'].endswith('.py'), 'COMPOSER_BACKEND_UNSUPPORTED')
            require(not contract['unresolved_symbols'], 'UNRESOLVED_SEGMENT_SYMBOLS')
            source = contained(root, contract['source_path'])
            require(source.stat().st_size <= MAX_EVIDENCE_BYTES, 'SOURCE_BUDGET')
            raw = source.read_bytes()
            require(digest(normalized(raw).encode()) == contract['parent_source_hash'], 'SEGMENT_PARENT_DRIFT')
            segments.append({'contract': contract, 'mutation_id': mutation_id})
    return sorted(segments, key=lambda s: (s['contract']['source_path'], s['contract']['reproduction_selector'], s['contract']['start_line'], s['mutation_id']))


def compose_source(root, segments, omit=None):
    """Compose independent assertion segments with their full ordered prefixes.

    Keep exact module/class context. Run each segment in its own unittest
    lifecycle, so setUp/tearDown and registered cleanup do not bleed between
    segments. Cross-module joins and custom test runners remain held.
    """
    require(2 <= len(segments) <= 8, 'SEGMENT_COUNT')
    paths = {s['contract']['source_path'] for s in segments}
    require(len(paths) == 1, 'CROSS_MODULE_CONTEXT_UNRESOLVED')
    source_path = next(iter(paths))
    source = contained(root, source_path)
    raw = source.read_bytes()
    require(all(digest(normalized(raw).encode()) == s['contract']['parent_source_hash'] for s in segments), 'SEGMENT_PARENT_DRIFT')
    tree = ast.parse(normalized(raw))
    classes = []
    methods = []
    for segment in segments:
        contract = segment['contract']
        selector = contract['reproduction_selector'].split('::')[-1]
        parts = selector.split('.')
        if len(parts) != 2:
            # Generic coals retain source coordinates rather than Python symbols.
            # Resolve only an unambiguous method enclosing the proven assertion.
            enclosing = [(cls.name, n.name) for cls in tree.body if isinstance(cls, ast.ClassDef) for n in cls.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test') and n.lineno <= contract['start_line'] <= n.end_lineno]
            require(len(enclosing) == 1, 'UNITTEST_METHOD_REQUIRED')
            parts = list(enclosing[0])
        class_name, method_name = parts
        matches = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name]
        require(len(matches) == 1, 'PARENT_CLASS_UNRESOLVED')
        cls = matches[0]
        require(not cls.decorator_list and len(cls.bases) == 1 and ast.unparse(cls.bases[0]) in ('unittest.TestCase', 'TestCase'), 'CUSTOM_TEST_LIFECYCLE_UNRESOLVED')
        require(not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in ('__init__', 'run') for n in cls.body), 'CUSTOM_TEST_LIFECYCLE_UNRESOLVED')
        require(not any(isinstance(n, ast.FunctionDef) and n.name in ('setUpModule', 'tearDownModule', 'load_tests') for n in tree.body), 'FIXTURE_CONTEXT_UNRESOLVED')
        parents = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name]
        require(len(parents) == 1 and not parents[0].decorator_list, 'PARENT_METHOD_UNRESOLVED')
        parent = parents[0]
        require(len(parent.args.args) == 1 and not parent.args.vararg and not parent.args.kwarg and not parent.args.kwonlyargs, 'PARAMETER_CONTEXT_UNRESOLVED')
        matching = [i for i, n in enumerate(parent.body) if n.lineno <= contract['start_line'] <= n.end_lineno]
        require(len(matching) == 1, 'SEGMENT_CONTEXT_UNRESOLVED')
        prefix = copy.deepcopy(parent.body[:matching[0] + 1])
        require(not any(isinstance(n, (ast.Return, ast.Yield, ast.YieldFrom, ast.Await, ast.Assert)) for p in prefix for n in ast.walk(p)), 'EARLY_EXIT_OR_OPTIMIZABLE_ASSERTION')
        require(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == 'self' and n.func.attr.startswith('assert') for p in prefix for n in ast.walk(p)), 'ASSERTION_CONTEXT_UNRESOLVED')
        method = copy.deepcopy(parent)
        method.name = 'test_franken_segment_' + str(len(methods))
        method.body = prefix
        methods.append(method)
        classes.append(class_name)
    require(len(set(classes)) == 1, 'CROSS_CLASS_CONTEXT_UNRESOLVED')
    require(len({s['contract']['fragment_id'] for s in segments}) == len(segments), 'DUPLICATE_SEGMENT')
    require(len({s['mutation_id'] for s in segments}) == len(segments), 'INDEPENDENT_CHALLENGES_REQUIRED')
    selected_class = classes[0]
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        cls.body = [n for n in cls.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) or not n.name.startswith('test')]
        if cls.name == selected_class:
            cls.body.extend(methods)
        if not cls.body:
            cls.body = [ast.Pass()]
    # Do not run original parent discovery/main blocks or original free tests.
    tree.body = [n for n in tree.body if not isinstance(n, ast.FunctionDef) or not n.name.startswith('test')]
    tree.body = [n for n in tree.body if not (isinstance(n, ast.If) and '__name__' in ast.unparse(n.test))]
    require(not any(isinstance(n, ast.ClassDef) and n.name == '_KilnFrankentest' for n in tree.body), 'GENERATED_SYMBOL_COLLISION')
    chosen = [m.name for i, m in enumerate(methods) if i != omit]
    runner = f"""
import unittest as _franken_unittest
_franken_observations = []
class _FrankenResult(_franken_unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.executed_ids = []
    def startTest(self, test):
        self.executed_ids.append(test.id())
        super().startTest(test)
class _KilnFrankentest(_franken_unittest.TestCase):
    def test_frankentest(self):
        _errors, _unproven, _failures = [], [], []
        for _name in {chosen!r}:
            _suite = _franken_unittest.TestSuite([{selected_class}(_name)])
            _result = _FrankenResult()
            _suite.run(_result)
            _franken_observations.append(dict(segment=_name, executed_ids=_result.executed_ids, failures=len(_result.failures), errors=len(_result.errors), tests=_result.testsRun, skipped=len(_result.skipped), expected_failures=len(_result.expectedFailures), unexpected_successes=len(_result.unexpectedSuccesses)))
            if _result.errors or _result.testsRun != 1:
                _errors.append(str(_result.errors))
            if _result.skipped or _result.expectedFailures or _result.unexpectedSuccesses:
                _unproven.append(_name)
            if _result.failures:
                _failures.append(str(_result.failures))
        if _errors:
            raise RuntimeError('FRANKENTEST_SEGMENT_EXECUTION_ERROR:' + str(_errors))
        if _unproven:
            self.skipTest('FRANKENTEST_SEGMENT_UNPROVEN:' + str(_unproven))
        if _failures:
            self.fail('FRANKENTEST_SEGMENT_ASSERTION:' + str(_failures))
if __name__ == '__main__':
    import unittest as _franken_unittest, json as _franken_json, sys as _franken_sys
    _franken_suite = _franken_unittest.TestSuite([_KilnFrankentest('test_frankentest')])
    _franken_result = _franken_unittest.TextTestRunner(verbosity=2).run(_franken_suite)
    print('KILN_FRANKENTEST_RESULT=' + _franken_json.dumps(dict(test_id='__main__._KilnFrankentest.test_frankentest', expected_segment_ids={[f'__main__.{selected_class}.{name}' for name in chosen], 'segments': _franken_observations}))
    _franken_sys.exit(2 if _franken_result.errors or _franken_result.skipped or _franken_result.expectedFailures or _franken_result.unexpectedSuccesses else 1 if _franken_result.failures else 0)
"""
    tree.body.extend(ast.parse(runner).body)
    return ast.unparse(ast.fix_missing_locations(tree)) + '\n', source_path


def execute_candidate(repository, relative, code, contract, timeout, optimized):
    path = contained(repository, relative)
    require(not path.exists(), 'GENERATED_PATH_ALREADY_EXISTS')
    path.write_text(code, encoding='utf-8', newline='\n')
    environment = sanitize_environment()
    environment.update({key: value.replace('{specimen}', str(repository)).replace('{entry}', relative) for key, value in contract.execution.environment})
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    deadline = time.monotonic() + timeout
    commands = [expand_contract_command(cmd, repository, relative) for cmd in contract.execution.rebuild_commands]
    command = [sys.executable, '-I', '-B']
    if optimized:
        command.append('-O')
    bootstrap = "import sys,runpy,pathlib;sys.path.insert(0,'.');p=pathlib.Path(sys.argv[1]);parts=p.parent.parts;packaged=bool(parts) and all(x.isidentifier() and pathlib.Path(*parts[:i+1],'__init__.py').exists() for i,x in enumerate(parts));sys.path.insert(0, str(p.parent));mod=runpy.run_path(str(p), run_name='__main__');"
    command += ['-c', bootstrap, relative]
    commands.append(command)
    outputs = []
    for index, cmd in enumerate(commands):
        result = subprocess.run(cmd, cwd=repository, env=environment, capture_output=True, text=True, timeout=max(0.001, deadline-time.monotonic()))
        outputs.append({'command': cmd, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode and index != len(commands)-1:
            return {'classification': 'EXECUTION_FAILED', 'processes': outputs}
    markers = [line.split('=', 1)[1] for line in result.stdout.splitlines() if line.startswith('KILN_FRANKENTEST_RESULT=')]
    if len(markers) != 1:
        return {'classification': 'EXECUTION_FAILED', 'processes': outputs}
    outcome = json.loads(markers[0])
    if not isinstance(outcome, dict):
        return {'classification': 'EXECUTION_FAILED', 'processes': outputs}
    expected_nodes = [n.value for n in ast.walk(ast.parse(code)) if isinstance(n, ast.keyword) and n.arg == 'expected_segment_ids']
    parent_expected = ast.literal_eval(expected_nodes[0]) if len(expected_nodes) == 1 else None
    valid = outcome.get('tests') == 1 and all(outcome.get(k) == 0 for k in ('errors', 'skipped', 'expected_failures', 'unexpected_successes'))
    expected_ids = outcome.get('expected_segment_ids')
    observations = outcome.get('segments')
    valid = valid and outcome.get('test_id') == '__main__._KilnFrankentest.test_frankentest' and isinstance(expected_ids, list) and expected_ids == parent_expected and isinstance(observations, list)
    if valid:
        valid = len(observations) == len(expected_ids) and [o.get('executed_ids') for o in observations] == [[name] for name in expected_ids] and all(o.get('tests') == 1 and all(o.get(k) == 0 for k in ('errors', 'skipped', 'expected_failures', 'unexpected_successes')) for o in observations)
    classification = 'EXECUTION_FAILED'
    if valid and result.returncode == 0 and outcome['failures'] == 0:
        classification = 'PASS'
    if valid and result.returncode == 1 and outcome['failures'] == 1:
        classification = 'ASSERTION_FAILURE'
    return {'classification': classification, 'result': outcome, 'processes': outputs}

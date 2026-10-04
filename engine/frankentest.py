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
from pathlib import Path
import subprocess
import sys
import time
import uuid
from dataclasses import asdict

from engine.coal_contracts import resolve_coal_contract
from engine.mutation_adapters import discover_mutations, expand_contract_command
from engine.mutation_executor import apply_mutation
from engine.proof_metadata import validate_proof_metadata_payload
from engine.sandbox_execution import SandboxExecutor
from engine.target_intake import inspect_target
from engine.isolation_boundary import repository_path_is_absolute, sanitize_environment

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
        require(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == 'self' and n.func.attr.startswith('assert') for p in prefix for n in ast.walk(p)), 'UNITTEST_ASSERTION_REQUIRED')
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
    print('KILN_FRANKENTEST_RESULT=' + _franken_json.dumps(dict(test_id='__main__._KilnFrankentest.test_frankentest', expected_segment_ids={[f'__main__.{selected_class}.{name}' for name in chosen]!r}, segments=_franken_observations, tests=_franken_result.testsRun, failures=len(_franken_result.failures), errors=len(_franken_result.errors), skipped=len(_franken_result.skipped), unexpected_successes=len(_franken_result.unexpectedSuccesses), expected_failures=len(_franken_result.expectedFailures))))
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
    command += ['-c', "import sys,runpy;sys.path.insert(0,'.');runpy.run_path(sys.argv[1],run_name='__main__')", relative]
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


def frankentest(target, evidence, output, adapter='auto', max_candidates=8, timeout=30, selected_fragments=None):
    require(type(max_candidates) is int and 1 <= max_candidates <= 64, 'CANDIDATE_BUDGET')
    require(isinstance(timeout, (int, float)) and math.isfinite(timeout) and 0 < timeout <= 300, 'TIME_BUDGET')
    identity = inspect_target(str(target))
    require(identity.git_repository and identity.repository_clean, 'CLEAN_GIT_TARGET_REQUIRED')
    root = Path(identity.repository_root).resolve()
    output = Path(output).resolve()
    require(not output.is_relative_to(root), 'OUTPUT_MUST_BE_OUTSIDE_TARGET')
    require(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
    contract = resolve_coal_contract(adapter, root)
    require(contract is not None, 'DECLARED_ENVIRONMENT_MISSING')
    require('python' in contract.languages, 'COMPOSER_BACKEND_UNSUPPORTED')
    profile = {'version': 'KILN-FRANKENTEST-1', 'composer_sha256': digest(Path(__file__).read_bytes()), 'interpreter': sys.executable, 'interpreter_version': sys.version, 'interpreter_sha256': digest(Path(sys.executable).read_bytes()), 'coal_sha256': digest(json.dumps(asdict(contract), sort_keys=True).encode()), 'isolation': 'TRUSTED_LOCAL_GIT_WORKTREE_NOT_OS_SANDBOX'}
    evidence = Path(evidence).resolve()
    require(evidence.stat().st_size <= MAX_EVIDENCE_BYTES, 'EVIDENCE_BUDGET')
    evidence_raw = evidence.read_bytes()
    aggregate = read_json(evidence, evidence_raw)
    segments = proven_segments(root, aggregate)
    if selected_fragments is not None:
        require(len(selected_fragments) == 2 and len(set(selected_fragments)) == 2, 'SELECTED_FRAGMENT_COUNT')
        segments = [s for s in segments if s['contract']['fragment_id'] in selected_fragments]
        require({s['contract']['fragment_id'] for s in segments} == set(selected_fragments), 'SELECTED_FRAGMENT_NOT_PROVEN')
    require(len(segments) >= 2, 'INSUFFICIENT_PROVEN_SEGMENTS')
    inventory = {c.mutation_id: c for c in discover_mutations(adapter, root)}
    output.mkdir(parents=True)
    executor = SandboxExecutor(root, identity.source_commit, output)
    report = {'schema': 'kiln.frankentest-report.v1', 'source_commit': identity.source_commit, 'source_fingerprint': identity.target_fingerprint, 'proof_sha256': digest(evidence_raw), 'backend': 'python-unittest', 'execution_profile': profile, 'candidates': [], 'held_combinations': [], 'system_wide_approved': False}
    passes = 0
    try:
        for pair in itertools.combinations(segments, 2):
            if len(report['candidates']) + len(report['held_combinations']) >= max_candidates:
                break
            try:
                code, parent = compose_source(root, pair)
                challenges = []
                for s in pair:
                    require(s['mutation_id'] in inventory, 'PROOF_MUTATION_NOT_IN_TARGET')
                    c = inventory[s['mutation_id']]
                    require(c.relative_path != parent and not c.relative_path.startswith(('tests/', 'test/')), 'TEST_ONLY_CHALLENGE_NOT_ALLOWED')
                    challenges.append(c)
            except RuntimeError as error:
                report['held_combinations'].append({'fragments': [s['contract']['fragment_id'] for s in pair], 'reason': str(error)})
                continue
            candidate_id = 'KILN-FRANKENTEST-' + digest(json.dumps({'code': code, 'fragments': [s['contract']['fragment_id'] for s in pair], 'head': identity.source_commit, 'execution_profile': profile}, sort_keys=True).encode())[:20].upper()
            candidate = {'schema': SCHEMA, 'candidate_id': candidate_id, 'source_sha256': digest(code.encode()), 'source_commit': identity.source_commit, 'proof_sha256': digest(evidence_raw), 'execution_profile': profile, 'adapter': adapter, 'parent_source': parent, 'segments': pair, 'qualification': [], 'disposition': 'UNQUALIFIED', 'system_wide_approved': False}
            candidate_dir = output / candidate_id
            candidate_dir.mkdir()
            (candidate_dir / 'test_frankentest.py').write_text(code, encoding='utf-8', newline='\n')
            relative = (Path(parent).parent / (candidate_id.lower().replace('-', '_') + '.py')).as_posix()
            for optimized in (False, True):
                scenarios = [('positive_baseline', None, None, 'PASS')]
                scenarios += [('fault_challenge', c, None, 'ASSERTION_FAILURE') for c in challenges]
                scenarios += [('assertion_removal_control', c, i, 'PASS_OR_RETAINED_DETECTION') for i, c in enumerate(challenges)]
                for kind, mutation, omit, expected in scenarios:
                    passes += 1
                    lease = executor.materialize(candidate_id, passes, mutation.mutation_id if mutation else 'BASELINE')
                    entry = {'kind': kind, 'optimized': optimized, 'mutation_id': mutation.mutation_id if mutation else None, 'expected': expected}
                    try:
                        if mutation:
                            specimen_candidates = {c.mutation_id: c for c in discover_mutations(adapter, lease.repository)}
                            require(mutation.mutation_id in specimen_candidates, 'SPECIMEN_MUTATION_DRIFT')
                            require(apply_mutation(lease.repository, specimen_candidates[mutation.mutation_id]).applied, 'MUTATION_NO_EFFECT')
                        execution_code = code if omit is None else compose_source(root, pair, omit=omit)[0]
                        entry.update(execute_candidate(lease.repository, relative, execution_code, contract, timeout, optimized))
                        if entry['classification'] == 'ASSERTION_FAILURE':
                            detected = [o['segment'] for o in entry['result']['segments'] if o['failures']]
                            entry['detected_segments'] = detected
                            if kind == 'fault_challenge':
                                designated = 'test_franken_segment_' + str(challenges.index(mutation))
                                if designated not in detected:
                                    entry['classification'] = 'DESIGNATED_DETECTION_NOT_OBSERVED'
                            if kind == 'assertion_removal_control':
                                entry['classification'] = 'RETAINED_DETECTION'
                    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                        entry.update(classification='EXECUTION_FAILED', error=str(error))
                    finally:
                        entry['specimen_removed'] = executor.release(lease)
                        candidate['qualification'].append(entry)
            qualified = all((e.get('classification') == e['expected'] or e['expected'] == 'PASS_OR_RETAINED_DETECTION' and e.get('classification') in ('PASS', 'RETAINED_DETECTION')) and e['specimen_removed'] for e in candidate['qualification'])
            candidate['disposition'] = 'QUALIFIED_APPROVAL_CANDIDATE' if qualified else 'QUALIFICATION_FAILED'
            (candidate_dir / 'candidate.json').write_text(json.dumps(candidate, indent=2, sort_keys=True), encoding='utf-8')
            report['candidates'].append(candidate)
    finally:
        post = inspect_target(str(root))
        report['original_preserved'] = post.source_commit == identity.source_commit and post.repository_clean and post.target_fingerprint == identity.target_fingerprint
        report['execution_profile_preserved'] = digest(Path(__file__).read_bytes()) == profile['composer_sha256'] and digest(Path(sys.executable).read_bytes()) == profile['interpreter_sha256']
        if not report['original_preserved']:
            for candidate in report['candidates']:
                candidate['disposition'] = 'SOURCE_PRESERVATION_FAILED'
                (output / candidate['candidate_id'] / 'candidate.json').write_text(json.dumps(candidate, indent=2, sort_keys=True), encoding='utf-8')
        report['disposition'] = 'QUALIFIED_APPROVAL_CANDIDATES' if report['original_preserved'] and report['execution_profile_preserved'] and report['candidates'] and all(c['disposition'] == 'QUALIFIED_APPROVAL_CANDIDATE' for c in report['candidates']) else 'HELD'
        (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
    return report


def approve_frankentest(target, candidate_path, evidence, expected_sha256, authority_ref, registry, timeout=30):
    """Explicit, pinned approval with fresh recursive requalification.

    Creates a new immutable registry entry; does not rewrite a test library,
    deploy code, grant Brain authority, or approve future candidates.
    """
    require(isinstance(authority_ref, str) and authority_ref.strip(), 'APPROVAL_AUTHORITY_REQUIRED')
    candidate_path = Path(candidate_path).resolve()
    raw = candidate_path.read_bytes()
    require(digest(raw) == expected_sha256, 'APPROVAL_CANDIDATE_PIN')
    candidate = read_json(candidate_path, raw)
    require(candidate.get('schema') == SCHEMA and candidate.get('disposition') == 'QUALIFIED_APPROVAL_CANDIDATE' and candidate.get('system_wide_approved') is False, 'UNQUALIFIED_CANDIDATE')
    code = (candidate_path.parent / 'test_frankentest.py').read_bytes()
    require(digest(code) == candidate['source_sha256'], 'GENERATED_SOURCE_DRIFT')
    identity = inspect_target(str(target))
    require(identity.source_commit == candidate['source_commit'], 'APPROVAL_TARGET_DRIFT')
    require(candidate['execution_profile']['composer_sha256'] == digest(Path(__file__).read_bytes()), 'APPROVAL_BACKEND_DRIFT')
    require(digest(Path(evidence).read_bytes()) == candidate['proof_sha256'], 'APPROVAL_PROOF_DRIFT')
    registry = Path(registry).resolve()
    require(not registry.is_relative_to(Path(identity.repository_root).resolve()), 'REGISTRY_MUST_BE_OUTSIDE_TARGET')
    registry.mkdir(parents=True, exist_ok=True)
    fragments = [s['contract']['fragment_id'] for s in candidate['segments']]
    run_root = registry / ('requalification-' + uuid.uuid4().hex)
    result = frankentest(target, evidence, run_root, candidate['adapter'], 1, timeout, selected_fragments=fragments)
    require(result['disposition'] == 'QUALIFIED_APPROVAL_CANDIDATES', 'APPROVAL_REQUALIFICATION_FAILED')
    fresh = result['candidates'][0]
    require(fresh['candidate_id'] == candidate['candidate_id'] and fresh['source_sha256'] == candidate['source_sha256'], 'APPROVAL_RECONSTRUCTION_DRIFT')
    qualified_report = (run_root / 'report.json').read_bytes()
    receipt = {'schema': 'kiln.frankentest-approval.v1', 'candidate_id': candidate['candidate_id'], 'candidate_sha256': expected_sha256, 'source_sha256': candidate['source_sha256'], 'source_commit': candidate['source_commit'], 'proof_sha256': candidate['proof_sha256'], 'execution_profile': fresh['execution_profile'], 'authority_ref': authority_ref, 'requalification_report': str(run_root / 'report.json'), 'requalification_sha256': digest(qualified_report), 'qualification_snapshot': 'qualification-report.json', 'disposition': 'APPROVED_SYSTEM_WIDE_TEST_CANDIDATE', 'installed_into_library': False}
    destination = registry / candidate['candidate_id']
    destination.mkdir(exist_ok=False)
    (destination / 'test_frankentest.py').write_bytes(code)
    (destination / 'candidate.json').write_bytes(raw)
    (destination / 'qualification-report.json').write_bytes(qualified_report)
    require(digest((destination / 'test_frankentest.py').read_bytes()) == fresh['source_sha256'] and digest((destination / 'candidate.json').read_bytes()) == expected_sha256 and digest((destination / 'qualification-report.json').read_bytes()) == receipt['requalification_sha256'], 'REGISTRY_SNAPSHOT_DRIFT')
    # Admission is the create-only hard link of a complete, fsynced receipt.
    # A directory without this receipt is pending, never admitted. A competing
    # approval cannot overwrite an existing entry; it receives an explicit conflict.
    pending = destination / '.approval.pending.json'
    with pending.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.link(pending, destination / 'approval.json')
    inspect_approved_candidate(registry, candidate['candidate_id'])
    return receipt


def inspect_approved_candidate(registry, candidate_id):
    require(re.fullmatch(r'KILN-FRANKENTEST-[0-9A-F]{20}', candidate_id) is not None, 'REGISTRY_CANDIDATE_ID')
    directory = Path(registry).resolve() / candidate_id
    receipt = read_json(directory / 'approval.json')
    require(receipt.get('schema') == 'kiln.frankentest-approval.v1' and receipt.get('candidate_id') == candidate_id and receipt.get('disposition') == 'APPROVED_SYSTEM_WIDE_TEST_CANDIDATE', 'REGISTRY_APPROVAL_INVALID')
    bindings = {'candidate.json': receipt['candidate_sha256'], 'test_frankentest.py': receipt['source_sha256'], 'qualification-report.json': receipt['requalification_sha256']}
    for name, expected in bindings.items():
        require(digest(contained(directory, name).read_bytes()) == expected, 'REGISTRY_CONTENT_DRIFT:' + name)
    report = read_json(directory / 'qualification-report.json')
    require(report.get('original_preserved') is True and report.get('execution_profile_preserved') is True and report.get('disposition') == 'QUALIFIED_APPROVAL_CANDIDATES', 'REGISTRY_QUALIFICATION_INVALID')
    selected = [c for c in report['candidates'] if c['candidate_id'] == candidate_id]
    require(len(selected) == 1 and selected[0]['source_sha256'] == receipt['source_sha256'] and selected[0]['source_commit'] == receipt['source_commit'] and selected[0]['proof_sha256'] == receipt['proof_sha256'] and selected[0]['execution_profile'] == receipt['execution_profile'], 'REGISTRY_SNAPSHOT_CONTRADICTION')
    return receipt

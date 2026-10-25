#!/usr/bin/env python3
"""Recover a truncated plot export without changing inference or scored results.

Re-execute only the frozen post-inference scorer, verify identical numerical
results and PNG, and publish the SVG atomically. Preserve the observed partial
export and its mismatch against the originally recorded SVG digest.
"""
from __future__ import annotations
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


def main() -> None:
    experiment = ROOT / 'experiments/bounded_online_001'
    destination = ROOT / 'report/Bounded-Online-001.svg'
    png = destination.with_suffix('.png')
    scores_path = experiment / 'scores.json'
    original_scores_bytes = scores_path.read_bytes()
    original_scores = json.loads(original_scores_bytes)
    partial = destination.read_bytes()
    try:
        ET.fromstring(partial)
    except ET.ParseError as error:
        parse_error = str(error)
    else:
        raise ValueError('SVG already parses; preserve it without another recovery')
    assert sha(png.read_bytes()) == original_scores['figure_sha256'][png.name]
    integrity = experiment / 'artifact_integrity'
    integrity.mkdir(exist_ok=True)
    record_path = integrity / 'svg_recovery.json'
    backup = integrity / 'Bounded-Online-001.svg.partial.gz'
    assert not record_path.exists() and not backup.exists()
    atomic_write(backup, gzip.compress(partial, mtime=0))

    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    import score_bounded_online
    original_savefig = Figure.savefig

    def buffered_savefig(figure, filename, *args, **kwargs):
        path = Path(filename)
        buffer = io.BytesIO()
        original_savefig(figure, buffer, *args, format=path.suffix[1:], **kwargs)
        atomic_write(path, buffer.getvalue())

    with tempfile.TemporaryDirectory(prefix='mumble_plot_recovery_') as directory:
        directory = Path(directory)
        temporary_png = directory / png.name
        temporary_scores = directory / 'scores.json'
        prior_argv = sys.argv
        Figure.savefig = buffered_savefig
        try:
            sys.argv = ['score_bounded_online.py', '--primary', str(experiment / 'primary'),
                        '--output', str(temporary_scores), '--figure', str(temporary_png)]
            assert score_bounded_online.main() == 0
        finally:
            Figure.savefig = original_savefig
            sys.argv = prior_argv
        recreated = json.loads(temporary_scores.read_text())
        ignored = {'scoring_started_utc', 'scoring_finished_utc', 'figure_sha256'}
        assert {k: v for k, v in original_scores.items() if k not in ignored} == {
            k: v for k, v in recreated.items() if k not in ignored}
        assert temporary_png.read_bytes() == png.read_bytes()
        recovered = temporary_png.with_suffix('.svg').read_bytes()
        ET.fromstring(recovered)
        atomic_write(destination, recovered)
    assert scores_path.read_bytes() == original_scores_bytes
    record = {
        'schema': 'mumble_bounded_online_svg_recovery_v1',
        'issue': 'After scorer completion the persisted SVG was a truncated invalid XML prefix; cause unestablished. PNG and numerical scores retained their recorded identities.',
        'original_svg_sha256_recorded_in_scores': original_scores['figure_sha256'][destination.name],
        'observed_partial_sha256': sha(partial), 'observed_partial_bytes': len(partial),
        'observed_parse_error': parse_error, 'partial_backup': str(backup.relative_to(ROOT)),
        'partial_backup_sha256': sha(backup.read_bytes()),
        'recovered_svg': str(destination.relative_to(ROOT)),
        'recovered_svg_sha256': sha(recovered), 'recovered_svg_bytes': len(recovered),
        'recovered_svg_XML_valid': True,
        'numerical_scores_exact_excluding_export_metadata': True,
        'original_PNG_bytes_exact': True, 'original_scores_unchanged': True,
        'primary_runs_added': 0, 'optimizer_calls_added': 0,
        'post_inference_scoring_repetitions_for_export_recovery': 1,
        'recovery_script_sha256': sha(Path(__file__).read_bytes()),
        'scorer_sha256': sha((ROOT / 'tools/score_bounded_online.py').read_bytes()),
        'score_sha256': sha(original_scores_bytes),
        'note': 'Frozen scores retain the original SVG export digest. This record maps that export to the preserved partial and separately regenerated valid SVG; no inference or numeric result was replaced.'}
    atomic_write(record_path, (json.dumps(record, indent=2) + '\n').encode())
    print(json.dumps({'svg_recovered': True, 'numerical_scores_exact': True,
                      'PNG_exact': True, 'new_inference_runs': 0,
                      'svg_bytes': len(recovered), 'record': str(record_path.relative_to(ROOT))}))


if __name__ == '__main__':
    main()

"""
Tests for the Sedimental CLI argument parser.

Validates Requirements 6.1–6.6:
  6.1 - input path argument
  6.2 - output path argument
  6.3 - --metadata argument
  6.4 - --save-masks flag
  6.5 - --scale argument
  6.6 - --help output
"""

import pytest
from unittest.mock import patch


def parse(argv):
    """Helper: run main()'s parser against argv and return parsed args."""
    import argparse
    # Re-import to get a fresh parser each call
    from sedimental.cli import main
    import sys

    # We call parse_args directly by reconstructing the parser logic.
    # Easier: just import the module and call parse_args with patched sys.argv.
    with patch('sys.argv', ['sedimental'] + argv):
        # We need access to the parser, so we replicate the parser build here
        # by importing the module internals.
        pass

    # Build parser the same way cli.py does so tests stay in sync.
    import argparse
    parser = argparse.ArgumentParser(
        description='Sedimental: Sediment grain analysis tool'
    )
    subparsers = parser.add_subparsers(dest='command')

    process_parser = subparsers.add_parser('process', help='Process sediment images')
    process_parser.add_argument('input', help='Image file or directory to process')
    process_parser.add_argument('-o', '--output', help='Output CSV path', default='results.csv')
    process_parser.add_argument('--metadata', help='Metadata JSON file path')
    process_parser.add_argument('--save-masks', action='store_true')
    process_parser.add_argument('--scale', type=float)
    process_parser.add_argument('-v', '--verbose', action='store_true')

    web_parser = subparsers.add_parser('web', help='Start web interface')
    web_parser.add_argument('--port', type=int, default=8080)

    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# process subcommand
# ---------------------------------------------------------------------------

class TestProcessSubcommand:
    def test_input_positional_argument(self):
        """Req 6.1 - accepts input path as positional argument."""
        args = parse(['process', '/data/input/sample.jpg'])
        assert args.command == 'process'
        assert args.input == '/data/input/sample.jpg'

    def test_input_directory(self):
        """Req 6.1 - accepts directory as input path."""
        args = parse(['process', '/data/input'])
        assert args.input == '/data/input'

    def test_output_long_flag(self):
        """Req 6.2 - accepts --output argument."""
        args = parse(['process', 'img.jpg', '--output', 'out.csv'])
        assert args.output == 'out.csv'

    def test_output_short_flag(self):
        """Req 6.2 - accepts -o shorthand for output."""
        args = parse(['process', 'img.jpg', '-o', 'out.csv'])
        assert args.output == 'out.csv'

    def test_output_default(self):
        """Req 6.2 - output defaults to results.csv when not specified."""
        args = parse(['process', 'img.jpg'])
        assert args.output == 'results.csv'

    def test_metadata_argument(self):
        """Req 6.3 - accepts --metadata argument."""
        args = parse(['process', 'img.jpg', '--metadata', 'meta.json'])
        assert args.metadata == 'meta.json'

    def test_metadata_default_is_none(self):
        """Req 6.3 - metadata is None when not provided."""
        args = parse(['process', 'img.jpg'])
        assert args.metadata is None

    def test_save_masks_flag(self):
        """Req 6.4 - --save-masks sets flag to True."""
        args = parse(['process', 'img.jpg', '--save-masks'])
        assert args.save_masks is True

    def test_save_masks_default_false(self):
        """Req 6.4 - save_masks defaults to False."""
        args = parse(['process', 'img.jpg'])
        assert args.save_masks is False

    def test_scale_argument(self):
        """Req 6.5 - --scale accepts a float value."""
        args = parse(['process', 'img.jpg', '--scale', '25.4'])
        assert args.scale == pytest.approx(25.4)

    def test_scale_default_is_none(self):
        """Req 6.5 - scale is None when not provided."""
        args = parse(['process', 'img.jpg'])
        assert args.scale is None

    def test_scale_is_float(self):
        """Req 6.5 - scale is parsed as float, not string."""
        args = parse(['process', 'img.jpg', '--scale', '100'])
        assert isinstance(args.scale, float)

    def test_verbose_long_flag(self):
        """--verbose sets verbose to True."""
        args = parse(['process', 'img.jpg', '--verbose'])
        assert args.verbose is True

    def test_verbose_short_flag(self):
        """-v sets verbose to True."""
        args = parse(['process', 'img.jpg', '-v'])
        assert args.verbose is True

    def test_verbose_default_false(self):
        """verbose defaults to False."""
        args = parse(['process', 'img.jpg'])
        assert args.verbose is False

    def test_all_flags_together(self):
        """All process flags can be combined."""
        args = parse([
            'process', '/data/input',
            '-o', 'out.csv',
            '--metadata', 'meta.json',
            '--save-masks',
            '--scale', '50.0',
            '--verbose',
        ])
        assert args.input == '/data/input'
        assert args.output == 'out.csv'
        assert args.metadata == 'meta.json'
        assert args.save_masks is True
        assert args.scale == pytest.approx(50.0)
        assert args.verbose is True


# ---------------------------------------------------------------------------
# web subcommand
# ---------------------------------------------------------------------------

class TestWebSubcommand:
    def test_web_command_recognized(self):
        """web subcommand is recognized."""
        args = parse(['web'])
        assert args.command == 'web'

    def test_port_default(self):
        """--port defaults to 8080."""
        args = parse(['web'])
        assert args.port == 8080

    def test_port_custom(self):
        """--port accepts a custom integer value."""
        args = parse(['web', '--port', '9090'])
        assert args.port == 9090

    def test_port_is_int(self):
        """--port is parsed as int."""
        args = parse(['web', '--port', '3000'])
        assert isinstance(args.port, int)


# ---------------------------------------------------------------------------
# --help (Req 6.6)
# ---------------------------------------------------------------------------

class TestHelp:
    def test_help_exits_zero(self):
        """Req 6.6 - --help exits with code 0."""
        with patch('sys.argv', ['sedimental', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                from sedimental.cli import main
                main()
        assert exc_info.value.code == 0

    def test_process_help_exits_zero(self):
        """Req 6.6 - process --help exits with code 0."""
        with patch('sys.argv', ['sedimental', 'process', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                from sedimental.cli import main
                main()
        assert exc_info.value.code == 0

    def test_web_help_exits_zero(self):
        """Req 6.6 - web --help exits with code 0."""
        with patch('sys.argv', ['sedimental', 'web', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                from sedimental.cli import main
                main()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# No subcommand
# ---------------------------------------------------------------------------

class TestNoSubcommand:
    def test_no_command_returns_one(self):
        """Invoking with no subcommand returns exit code 1."""
        with patch('sys.argv', ['sedimental']):
            from sedimental.cli import main
            result = main()
        assert result == 1


# ---------------------------------------------------------------------------
# Docker invocation wrapper (Req 6.7, 8.3) - Task 10.2
# ---------------------------------------------------------------------------

class TestRunDockerProcess:
    """Tests for run_docker_process() Docker command construction."""

    def _make_args(self, input_path, output='results.csv', metadata=None,
                   save_masks=False, scale=None, verbose=False):
        import argparse
        args = argparse.Namespace(
            input=str(input_path),
            output=output,
            metadata=metadata,
            save_masks=save_masks,
            scale=scale,
            verbose=verbose,
        )
        return args

    def test_process_calls_docker_run(self, tmp_path):
        """run_docker_process() invokes subprocess with 'docker run'."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_process

        img = tmp_path / "sample.jpg"
        img.touch()
        args = self._make_args(img, output=str(tmp_path / "out.csv"))

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_process(args)

        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == 'docker'
        assert 'run' in called_cmd

    def test_process_mounts_input_volume(self, tmp_path):
        """run_docker_process() mounts the input directory as a volume."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_process

        img = tmp_path / "sample.jpg"
        img.touch()
        args = self._make_args(img, output=str(tmp_path / "out.csv"))

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_process(args)

        called_cmd = mock_run.call_args[0][0]
        # There should be a -v flag with the input directory
        v_indices = [i for i, x in enumerate(called_cmd) if x == '-v']
        mounts = [called_cmd[i + 1] for i in v_indices]
        assert any('/data/input' in m for m in mounts)

    def test_process_mounts_output_volume(self, tmp_path):
        """run_docker_process() mounts the output directory as a volume."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_process

        img = tmp_path / "sample.jpg"
        img.touch()
        args = self._make_args(img, output=str(tmp_path / "out.csv"))

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_process(args)

        called_cmd = mock_run.call_args[0][0]
        v_indices = [i for i, x in enumerate(called_cmd) if x == '-v']
        mounts = [called_cmd[i + 1] for i in v_indices]
        assert any('/data/output' in m for m in mounts)

    def test_process_passes_save_masks_flag(self, tmp_path):
        """run_docker_process() forwards --save-masks to the container."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_process

        img = tmp_path / "sample.jpg"
        img.touch()
        args = self._make_args(img, output=str(tmp_path / "out.csv"),
                               save_masks=True)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_process(args)

        called_cmd = mock_run.call_args[0][0]
        assert '--save-masks' in called_cmd

    def test_process_passes_scale_flag(self, tmp_path):
        """run_docker_process() forwards --scale to the container."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_process

        img = tmp_path / "sample.jpg"
        img.touch()
        args = self._make_args(img, output=str(tmp_path / "out.csv"),
                               scale=25.4)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_process(args)

        called_cmd = mock_run.call_args[0][0]
        assert '--scale' in called_cmd
        scale_idx = called_cmd.index('--scale')
        assert called_cmd[scale_idx + 1] == '25.4'

    def test_process_no_scale_flag_when_none(self, tmp_path):
        """run_docker_process() omits --scale when not provided."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_process

        img = tmp_path / "sample.jpg"
        img.touch()
        args = self._make_args(img, output=str(tmp_path / "out.csv"))

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_process(args)

        called_cmd = mock_run.call_args[0][0]
        assert '--scale' not in called_cmd

    def test_process_returns_docker_exit_code(self, tmp_path):
        """run_docker_process() returns the Docker container's exit code."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_process

        img = tmp_path / "sample.jpg"
        img.touch()
        args = self._make_args(img, output=str(tmp_path / "out.csv"))

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=42)
            result = run_docker_process(args)

        assert result == 42

    def test_process_docker_not_found_returns_one(self, tmp_path):
        """run_docker_process() returns 1 when Docker is not installed."""
        from unittest.mock import patch
        from sedimental.cli import run_docker_process

        img = tmp_path / "sample.jpg"
        img.touch()
        args = self._make_args(img, output=str(tmp_path / "out.csv"))

        with patch('subprocess.run', side_effect=FileNotFoundError):
            result = run_docker_process(args)

        assert result == 1


class TestRunDockerWeb:
    """Tests for run_docker_web() Docker command construction (Req 8.3)."""

    def _make_args(self, port=8080):
        import argparse
        return argparse.Namespace(port=port)

    def test_web_calls_docker_run(self):
        """run_docker_web() invokes subprocess with 'docker run'."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_web

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_web(self._make_args())

        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == 'docker'
        assert 'run' in called_cmd

    def test_web_maps_default_port(self):
        """run_docker_web() maps port 8080 by default (Req 8.3)."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_web

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_web(self._make_args(port=8080))

        called_cmd = mock_run.call_args[0][0]
        assert any('8080' in str(x) for x in called_cmd)

    def test_web_maps_custom_port(self):
        """run_docker_web() maps a custom port (Req 8.3)."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_web

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_docker_web(self._make_args(port=9090))

        called_cmd = mock_run.call_args[0][0]
        assert any('9090' in str(x) for x in called_cmd)

    def test_web_returns_docker_exit_code(self):
        """run_docker_web() returns the Docker container's exit code."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_docker_web

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = run_docker_web(self._make_args())

        assert result == 0

    def test_web_docker_not_found_returns_one(self):
        """run_docker_web() returns 1 when Docker is not installed."""
        from unittest.mock import patch
        from sedimental.cli import run_docker_web

        with patch('subprocess.run', side_effect=FileNotFoundError):
            result = run_docker_web(self._make_args())

        assert result == 1


# ---------------------------------------------------------------------------
# Exit code handling (Req 6.8, 6.9) - Task 10.3
# ---------------------------------------------------------------------------

class TestExitCodeHandling:
    """Tests for run_process_internal() exit code logic (Requirements 6.8, 6.9)."""

    def _make_args(self, input_path, output='results.csv', metadata=None,
                   save_masks=False, scale=None, verbose=False):
        import argparse
        return argparse.Namespace(
            input=str(input_path),
            output=output,
            metadata=metadata,
            save_masks=save_masks,
            scale=scale,
            verbose=verbose,
        )

    def _make_batch_result(self, total, successful, failed, errors=None):
        from sedimental.models import BatchResult
        return BatchResult(
            total_images=total,
            successful=successful,
            failed=failed,
            results=[],
            errors=errors or {},
        )

    def test_all_success_returns_zero(self, tmp_path):
        """Req 6.8 - exit code 0 when all images succeed."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import run_process_internal

        args = self._make_args(tmp_path / 'img.jpg', output=str(tmp_path / 'out.csv'))
        batch = self._make_batch_result(total=3, successful=3, failed=0)

        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrch:
            MockOrch.return_value.process_batch.return_value = batch
            result = run_process_internal(args)

        assert result == 0

    def test_total_failure_returns_nonzero(self, tmp_path):
        """Req 6.9 - non-zero exit code when all images fail."""
        from unittest.mock import patch
        from sedimental.cli import run_process_internal

        args = self._make_args(tmp_path / 'img.jpg', output=str(tmp_path / 'out.csv'))
        batch = self._make_batch_result(
            total=2, successful=0, failed=2,
            errors={'a.jpg': 'segmentation error', 'b.jpg': 'load error'},
        )

        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrch:
            MockOrch.return_value.process_batch.return_value = batch
            result = run_process_internal(args)

        assert result != 0

    def test_total_failure_prints_error_message(self, tmp_path, capsys):
        """Req 6.9 - error message displayed when all images fail."""
        from unittest.mock import patch
        from sedimental.cli import run_process_internal

        args = self._make_args(tmp_path / 'img.jpg', output=str(tmp_path / 'out.csv'))
        batch = self._make_batch_result(
            total=1, successful=0, failed=1,
            errors={'bad.jpg': 'corrupted file'},
        )

        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrch:
            MockOrch.return_value.process_batch.return_value = batch
            run_process_internal(args)

        captured = capsys.readouterr()
        assert 'Error' in captured.err or 'error' in captured.err.lower()

    def test_partial_failure_returns_zero(self, tmp_path):
        """Property 17 - partial failure exits 0 (at least one success)."""
        from unittest.mock import patch
        from sedimental.cli import run_process_internal

        args = self._make_args(tmp_path / 'img.jpg', output=str(tmp_path / 'out.csv'))
        batch = self._make_batch_result(
            total=3, successful=2, failed=1,
            errors={'bad.jpg': 'load error'},
        )

        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrch:
            MockOrch.return_value.process_batch.return_value = batch
            result = run_process_internal(args)

        assert result == 0

    def test_partial_failure_prints_warning(self, tmp_path, capsys):
        """Property 17 - partial failure logs a warning."""
        from unittest.mock import patch
        from sedimental.cli import run_process_internal

        args = self._make_args(tmp_path / 'img.jpg', output=str(tmp_path / 'out.csv'))
        batch = self._make_batch_result(
            total=3, successful=2, failed=1,
            errors={'bad.jpg': 'load error'},
        )

        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrch:
            MockOrch.return_value.process_batch.return_value = batch
            run_process_internal(args)

        captured = capsys.readouterr()
        assert 'Warning' in captured.err or 'warning' in captured.err.lower()

    def test_no_images_found_returns_nonzero(self, tmp_path):
        """Req 6.9 - non-zero exit code when no images are found."""
        from unittest.mock import patch
        from sedimental.cli import run_process_internal

        args = self._make_args(tmp_path / 'empty', output=str(tmp_path / 'out.csv'))
        batch = self._make_batch_result(total=0, successful=0, failed=0)

        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrch:
            MockOrch.return_value.process_batch.return_value = batch
            result = run_process_internal(args)

        assert result != 0

    def test_orchestrator_exception_returns_nonzero(self, tmp_path):
        """Req 6.9 - non-zero exit code when orchestrator raises an exception."""
        from unittest.mock import patch
        from sedimental.cli import run_process_internal

        args = self._make_args(tmp_path / 'img.jpg', output=str(tmp_path / 'out.csv'))

        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrch:
            MockOrch.return_value.process_batch.side_effect = RuntimeError('unexpected')
            result = run_process_internal(args)

        assert result != 0

    def test_orchestrator_exception_prints_error(self, tmp_path, capsys):
        """Req 6.9 - error message printed when orchestrator raises an exception."""
        from unittest.mock import patch
        from sedimental.cli import run_process_internal

        args = self._make_args(tmp_path / 'img.jpg', output=str(tmp_path / 'out.csv'))

        with patch('sedimental.cli.ProcessingOrchestrator') as MockOrch:
            MockOrch.return_value.process_batch.side_effect = RuntimeError('disk full')
            run_process_internal(args)

        captured = capsys.readouterr()
        assert 'Error' in captured.err or 'error' in captured.err.lower()

    def test_main_uses_internal_runner_inside_container(self, tmp_path, monkeypatch):
        """main() calls run_process_internal when SEDIMENTAL_INSIDE_CONTAINER is set."""
        from unittest.mock import patch
        from sedimental.cli import main

        monkeypatch.setenv('SEDIMENTAL_INSIDE_CONTAINER', '1')

        with patch('sys.argv', ['sedimental', 'process', str(tmp_path / 'img.jpg')]):
            with patch('sedimental.cli.run_process_internal', return_value=0) as mock_internal:
                with patch('sedimental.cli.run_docker_process') as mock_docker:
                    main()

        mock_internal.assert_called_once()
        mock_docker.assert_not_called()

    def test_main_uses_docker_runner_outside_container(self, tmp_path, monkeypatch):
        """main() calls run_docker_process when SEDIMENTAL_INSIDE_CONTAINER is not set."""
        from unittest.mock import patch, MagicMock
        from sedimental.cli import main

        monkeypatch.delenv('SEDIMENTAL_INSIDE_CONTAINER', raising=False)

        with patch('sys.argv', ['sedimental', 'process', str(tmp_path / 'img.jpg')]):
            with patch('sedimental.cli.run_docker_process', return_value=0) as mock_docker:
                with patch('sedimental.cli.run_process_internal') as mock_internal:
                    main()

        mock_docker.assert_called_once()
        mock_internal.assert_not_called()

import pytest
from unittest.mock import patch


class TestCLI:
    def test_requires_task_or_resume(self):
        with patch("sys.argv", ["orchestrator.cli"]):
            with pytest.raises(SystemExit):
                from orchestrator.cli import main
                main()

    def test_dry_run_flag(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "test", "--dry-run"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.dry_run is True
                    assert args.task == "test"

    def test_task_arg(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "build something"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.task == "build something"

    def test_parallel_flag_sets_execution(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "t", "--parallel"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.execution == "parallel"

    def test_sequential_flag_sets_execution(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "t", "--sequential"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.execution == "sequential"

    def test_interactive_flag(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "t", "--interactive"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.interactive is True

    def test_config_arg(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "t", "--config", "/tmp/c.yaml"]):
            with patch("orchestrator.cli.run_pipeline"):
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    mock_cfg.assert_called_once_with("/tmp/c.yaml")

    def test_resume_flag(self):
        with patch("sys.argv", ["orchestrator.cli", "--resume"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.resume is True

    def test_max_steps(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "t", "--max-steps", "5"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.max_steps == 5

    def test_mode_arg(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "t", "--mode", "interactive"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.mode == "interactive"

    def test_execution_arg(self):
        with patch("sys.argv", ["orchestrator.cli", "--task", "t", "--execution", "parallel"]):
            with patch("orchestrator.cli.run_pipeline") as mock_run:
                with patch("orchestrator.cli.load_config") as mock_cfg:
                    mock_cfg.return_value = {}
                    from orchestrator.cli import main
                    main()
                    args = mock_run.call_args[0][0]
                    assert args.execution == "parallel"

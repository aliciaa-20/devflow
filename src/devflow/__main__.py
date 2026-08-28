from devflow.config import Config
from devflow.input import accept_input
from devflow.models.repository import RepositoryInputError
from devflow.models.change import ChangeRequestError
from devflow.context import build_context
from devflow.history import build_historical_context
from devflow.impact import build_impact_analysis


def main() -> None:
    config = Config()
    print(f"DevFlow {config.version}")
    print()

    # ------------------------------------------------------------------
    # Phase 1 demo: validate repository + change description.
    # ------------------------------------------------------------------
    print("=== Phase 1: Repository + Change Input ===")
    examples = [
        {
            "url": "https://github.com/example/my-project",
            "description": "Refactor authentication session handling.",
            "changed_files": ["src/auth/session.py", "tests/test_session.py"],
        },
        {
            "url": "https://github.com/another-org/api-service.git",
            "description": "Add rate limiting to the public API endpoints.",
            "changed_files": [],
        },
    ]

    for ex in examples:
        try:
            repo, change = accept_input(
                ex["url"],
                ex["description"],
                ex.get("changed_files"),
            )
            print("Repository input accepted:")
            print(f"  URL:   {repo.url}")
            print(f"  Owner: {repo.owner}")
            print(f"  Name:  {repo.name}")
            print("Change request accepted:")
            print(f"  Description:   {change.description}")
            print(f"  Changed files: {list(change.changed_files) or '(none supplied)'}")
        except (RepositoryInputError, ChangeRequestError) as exc:
            print(f"Input error: {exc}")
        print()

    # Demonstrate rejection of an invalid URL.
    print("--- Invalid URL rejection ---")
    try:
        accept_input("not-a-url", "Some change")
    except RepositoryInputError as exc:
        print(f"Rejected (expected): {exc}")

    print()

    # ------------------------------------------------------------------
    # Phase 2 demo: context reconstruction.
    # ------------------------------------------------------------------
    print("=== Phase 2: Context Reconstruction ===")
    print(
        "To run a real context reconstruction, call build_context() with a "
        "RepositoryInput and ChangeRequest.\n"
        "Example (requires network access and git):\n"
        "\n"
        "  from devflow.input import accept_input\n"
        "  from devflow.context import build_context\n"
        "\n"
        "  repo, change = accept_input(\n"
        "      'https://github.com/pallets/flask',\n"
        "      'Refactor request context handling.',\n"
        "  )\n"
        "  ctx = build_context(repo, change)\n"
        "  print(ctx.artifacts)\n"
    )
    print(
        "Phase 2 smoke test: pass a real URL via the build_context() API.\n"
        "The __main__ demo does not perform live cloning to avoid mandatory\n"
        "network dependency in the entry-point demo."
    )

    # ------------------------------------------------------------------
    # Phase 3 demo: historical context.
    # ------------------------------------------------------------------
    print()
    print("=== Phase 3: Historical Context ===")
    print(
        "To run historical context extraction, call build_historical_context() with a\n"
        "RepositoryInput and RepositoryContext produced by Phase 2.\n"
        "Example (requires network access and git):\n"
        "\n"
        "  from devflow.input import accept_input\n"
        "  from devflow.context import build_context\n"
        "  from devflow.history import build_historical_context\n"
        "\n"
        "  repo, change = accept_input(\n"
        "      'https://github.com/pallets/flask',\n"
        "      'Refactor request context handling.',\n"
        "  )\n"
        "  ctx = build_context(repo, change)\n"
        "  history = build_historical_context(repo, ctx)\n"
        "  print(history.total_commits_found, 'commits found')\n"
        "  for art_hist in history.artifacts_with_history():\n"
        "      print(art_hist.artifact_path, ':', len(art_hist.commits), 'commits')\n"
    )
    print(
        "Phase 3 smoke test: run smoke_test_phase3.py with a real repository URL.\n"
        "The __main__ demo does not perform live cloning to avoid mandatory\n"
        "network dependency in the entry-point demo."
    )

    # ------------------------------------------------------------------
    # Phase 4 demo: impact analysis.
    # ------------------------------------------------------------------
    print()
    print("=== Phase 4: Impact Analysis ===")
    print(
        "To run impact analysis, call build_impact_analysis() with the\n"
        "RepositoryContext produced by Phase 2 and (optionally) the\n"
        "RepositoryHistory produced by Phase 3.\n"
        "Example (requires network access and git):\n"
        "\n"
        "  from devflow.input import accept_input\n"
        "  from devflow.context import build_context\n"
        "  from devflow.history import build_historical_context\n"
        "  from devflow.impact import build_impact_analysis\n"
        "\n"
        "  repo, change = accept_input(\n"
        "      'https://github.com/encode/httpx',\n"
        "      'Improve connection pooling behavior for async clients.',\n"
        "  )\n"
        "  ctx = build_context(repo, change)\n"
        "  hist = build_historical_context(repo, ctx)\n"
        "  impact = build_impact_analysis(ctx, hist)\n"
        "  print(len(impact.findings), 'impact findings')\n"
        "  for f in impact.confirmed_findings():\n"
        "      print(f.affected_artifact, f.relationship.value)\n"
    )
    print(
        "Phase 4 smoke test: run smoke_test_phase4.py with a real repository URL.\n"
        "The __main__ demo does not perform live cloning to avoid mandatory\n"
        "network dependency in the entry-point demo."
    )


if __name__ == "__main__":
    main()

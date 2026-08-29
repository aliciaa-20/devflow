import logging
import sys

from devflow.config import Config
from devflow.context import build_context
from devflow.history import build_historical_context
from devflow.impact import build_impact_analysis
from devflow.input import accept_input
from devflow.map import build_change_impact_map, open_html_in_browser, write_frontend_graph_payload
from devflow.models.change import ChangeRequestError
from devflow.models.repository import RepositoryInputError
from devflow.report import build_developer_report, write_frontend_report_payload
from devflow.risk import build_risk_analysis
from devflow.server import serve_forever, start_server

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def _read_cli_inputs(argv: list[str] | None = None) -> tuple[str, str]:
    args = [] if argv is None else list(argv)
    if len(args) == 2:
        return args[0], args[1]
    if len(args) == 0:
        if sys.stdin is not None and hasattr(sys.stdin, 'isatty') and sys.stdin.isatty():
            repository_url = input('GitHub repository URL:\n> ').strip()
            developer_change = input('Developer change:\n> ').strip()
            return repository_url, developer_change
        return (
            'https://github.com/pallets/flask',
            'Refactor request context handling.',
        )
    raise ValueError('Usage: python -m devflow [github_url] ["change description"]')


def _analyze_repository(repository_url: str, change_description: str):
    repo, change = accept_input(repository_url, change_description)
    context = build_context(repo, change)
    if context.error:
        raise ValueError(context.error)

    history = build_historical_context(repo, context)
    impact = build_impact_analysis(context, history)
    if impact.error:
        raise ValueError(impact.error)

    risk = build_risk_analysis(impact, context, history)
    graph = build_change_impact_map(context, impact, risk, history)
    if graph.error:
        raise ValueError(graph.error)

    report = build_developer_report(context, impact, risk, history)
    write_frontend_graph_payload(graph)
    write_frontend_report_payload(report)
    return graph, report


def main(argv: list[str] | None = None) -> int:
    config = Config()
    print(f'DevFlow {config.version}')
    print()
    print('Starting DevFlow interactive Change Impact Map interface...')
    print()

    try:
        repository_url, change_description = _read_cli_inputs(argv)
    except ValueError as exc:
        print(f'Error: {exc}')
        return 1

    if not repository_url or not change_description:
        print('Error: GitHub repository URL and developer change are required.')
        return 1

    print('Analyzing repository...')
    try:
        graph, _report = _analyze_repository(repository_url, change_description)
    except (RepositoryInputError, ChangeRequestError, ValueError) as exc:
        print(f'Error: {exc}')
        return 1

    print(f'Graph generated for: {graph.repository_url or repository_url}')
    url = 'http://127.0.0.1:8765/'
    server = start_server(host='127.0.0.1', port=8765, auto_open_browser=False)
    print('Server started. Press Ctrl+C to stop.')
    print('Opening Change Impact Map...')

    opened = open_html_in_browser(url)
    if not opened:
        print(f'Open this URL manually: {url}')

    print('Press Ctrl+C to stop DevFlow.')
    try:
        serve_forever(server)
    except KeyboardInterrupt:
        print('\nDevFlow stopped.')
        server.shutdown()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print('\nDevFlow stopped.')
        raise SystemExit(0)
    except Exception as exc:
        print(f'DevFlow error: {exc}', file=sys.stderr)
        raise SystemExit(1)

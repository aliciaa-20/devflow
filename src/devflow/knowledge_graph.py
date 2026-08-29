"""Repository knowledge graph builder using real repository structure and static evidence."""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from devflow.context.inspector import classify_file, walk_repository
from devflow.context.retriever import RepositoryRetrievalError, RetrievedRepository
from devflow.models.context import ArtifactKind
from devflow.models.repository import RepositoryInput
from devflow.models.repository_graph import (
    RepositoryGraphEdge,
    RepositoryGraphEvidence,
    RepositoryGraphNode,
    RepositoryKnowledgeGraph,
    RepositoryNodeType,
    RepositoryRelationshipType,
)


def _find_repo_root(tmpdir: Path, name: str) -> Path:
    candidate = tmpdir / name
    if candidate.is_dir():
        return candidate
    alt = tmpdir / name.removesuffix(".git")
    if alt.is_dir():
        return alt
    subdirs = [p for p in tmpdir.iterdir() if p.is_dir()]
    return subdirs[0] if subdirs else tmpdir


def _node_type_for_kind(kind: ArtifactKind) -> RepositoryNodeType:
    mapping = {
        ArtifactKind.SOURCE: RepositoryNodeType.SOURCE,
        ArtifactKind.TEST: RepositoryNodeType.TEST,
        ArtifactKind.CONFIGURATION: RepositoryNodeType.CONFIGURATION,
        ArtifactKind.DOCUMENTATION: RepositoryNodeType.DOCUMENTATION,
        ArtifactKind.DEPENDENCY: RepositoryNodeType.DEPENDENCY,
    }
    return mapping.get(kind, RepositoryNodeType.DIRECTORY)


def _resolve_internal_import(root_dir: Path, current_rel_path: str, import_name: str, repo_files: set[str]) -> str | None:
    current_file = root_dir / current_rel_path
    candidates: list[Path] = []
    if import_name.startswith("."):
        base = (current_file.parent / import_name).resolve()
        candidates.extend([base, base.with_suffix(".py"), base / "__init__.py"])
    else:
        module_path = import_name.replace(".", "/")
        candidates.extend([
            (root_dir / module_path).resolve(),
            (root_dir / f"{module_path}.py").resolve(),
            (root_dir / module_path / "__init__.py").resolve(),
        ])

    for candidate in candidates:
        try:
            rel = candidate.relative_to(root_dir).as_posix()
        except ValueError:
            continue
        if rel in repo_files:
            return rel
        if rel.endswith("/__init__.py"):
            package_rel = rel.rsplit("/__init__.py", 1)[0]
            if package_rel in repo_files:
                return package_rel
    return None


def _python_imports_for_file(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, ValueError):
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _js_imports_for_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    pattern = re.compile(
        r"(?:import|export)\s+(?:[^'\"]+?\s+from\s+)?['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)"
    )
    imports: list[str] = []
    for match in pattern.findall(text):
        for item in match:
            if item:
                imports.append(item)
    return imports


def _dependency_manifest_names(root_dir: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for manifest_name in ('requirements.txt', 'pyproject.toml', 'package.json', 'setup.py', 'setup.cfg', 'Pipfile'):
        manifest = root_dir / manifest_name
        if not manifest.exists():
            continue
        try:
            text = manifest.read_text(encoding="utf-8")
        except OSError:
            continue
        if manifest_name == 'package.json':
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            for section_name in ('dependencies', 'devDependencies', 'peerDependencies'):
                for dep_name in payload.get(section_name, {}):
                    names[str(dep_name)] = str(dep_name)
            continue
        if manifest_name == 'requirements.txt':
            for raw in text.splitlines():
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                dep = line.split(';', 1)[0].split('=', 1)[0].strip().replace(' ', '')
                if dep:
                    names[dep] = dep
            continue
        for candidate in re.findall(r"['\"]([A-Za-z0-9_.@/-]+)['\"]", text):
            if candidate and not candidate.startswith('.'):
                names[candidate] = candidate
    return names


def _root_to_dir_path(path: str) -> str:
    parent = Path(path).parent
    return parent.as_posix() if str(parent) != '.' else ''


def build_repository_knowledge_graph(
    repository_url: str,
    *,
    clone_timeout: int = 120,
    local_root: str | Path | None = None,
) -> RepositoryKnowledgeGraph:
    graph = RepositoryKnowledgeGraph(repository_url=repository_url, owner='unknown', name='repository')
    try:
        repository = RepositoryInput.from_url(repository_url)
    except ValueError as exc:
        graph.error = str(exc)
        return graph

    graph.owner = repository.owner
    graph.name = repository.name

    root_dir: Path | None = Path(local_root) if local_root is not None else None
    cleanup_required = False
    retrieved = None
    if root_dir is None:
        try:
            retrieved = RetrievedRepository.clone(
                url=repository.url,
                owner=repository.owner,
                name=repository.name,
                timeout=clone_timeout,
            )
            root_dir = _find_repo_root(retrieved.path, repository.name)
            cleanup_required = True
        except RepositoryRetrievalError as exc:
            graph.error = str(exc)
            return graph

    if root_dir is None or not root_dir.exists():
        graph.error = 'Repository root could not be resolved.'
        return graph

    try:
        all_files, _ = walk_repository(root_dir)
        repo_files = {p.replace('\\', '/') for p in all_files if p and p != '.'}
        repo_root_id = f'repository:{repository.owner}/{repository.name}'
        repo_root = RepositoryGraphNode(
            id=repo_root_id,
            label=f'{repository.owner}/{repository.name}',
            node_type=RepositoryNodeType.REPOSITORY,
            description='Repository root discovered from the supplied GitHub URL.',
            metadata={'path': '.', 'repository': f'{repository.owner}/{repository.name}', 'url': repository.url},
        )
        node_map: dict[str, RepositoryGraphNode] = {repo_root_id: repo_root}
        edge_map: dict[tuple[str, str, str], RepositoryGraphEdge] = {}

        def add_node(node: RepositoryGraphNode) -> None:
            node_map[node.id] = node

        def add_edge(
            source: str,
            target: str,
            relationship: RepositoryRelationshipType,
            description: str,
            evidence: tuple[RepositoryGraphEvidence, ...] = (),
        ) -> None:
            edge_key = (source, target, relationship.value)
            if edge_key in edge_map:
                return
            edge_map[edge_key] = RepositoryGraphEdge(
                source=source,
                target=target,
                relationship=relationship,
                description=description,
                evidence=evidence,
            )

        def ensure_directory(dir_rel: str) -> str:
            dir_id = f'directory:{dir_rel}'
            if dir_id not in node_map:
                add_node(
                    RepositoryGraphNode(
                        id=dir_id,
                        label=dir_rel,
                        node_type=RepositoryNodeType.DIRECTORY,
                        description=f'Directory module {dir_rel}.',
                        metadata={'path': dir_rel, 'repository': f'{repository.owner}/{repository.name}'},
                    )
                )
            return dir_id

        for rel_path in sorted(repo_files):
            kind = classify_file(rel_path)
            if kind == ArtifactKind.OTHER:
                continue
            node_id = f'{_node_type_for_kind(kind).value}:{rel_path}'
            add_node(
                RepositoryGraphNode(
                    id=node_id,
                    label=rel_path,
                    node_type=_node_type_for_kind(kind),
                    description=f'{kind.value.title()} file discovered in the repository.',
                    metadata={'path': rel_path, 'repository': f'{repository.owner}/{repository.name}', 'kind': kind.value, 'parent': _root_to_dir_path(rel_path)},
                )
            )
            parent = _root_to_dir_path(rel_path)
            if parent:
                dir_id = ensure_directory(parent)
                add_edge(dir_id, node_id, RepositoryRelationshipType.CONTAINS, f'{parent} contains {rel_path}.', ())
            else:
                add_edge(repo_root_id, node_id, RepositoryRelationshipType.CONTAINS, f'Repository root contains {rel_path}.', ())

        for rel_path in sorted(repo_files):
            parent = _root_to_dir_path(rel_path)
            if not parent:
                continue
            parent_dirs = [parent]
            current = parent
            while True:
                next_parent = _root_to_dir_path(current)
                if not next_parent:
                    break
                parent_dirs.append(next_parent)
                current = next_parent
            for ancestor in reversed(parent_dirs):
                ancestor_id = ensure_directory(ancestor)
                current_dir = ensure_directory(parent)
                if ancestor_id != current_dir:
                    add_edge(ancestor_id, current_dir, RepositoryRelationshipType.CONTAINS, f'{ancestor} contains {parent}.', ())

        for rel_path in sorted(repo_files):
            kind = classify_file(rel_path)
            if kind not in (ArtifactKind.SOURCE, ArtifactKind.TEST):
                continue
            full_path = root_dir / rel_path
            imports = _python_imports_for_file(full_path) if rel_path.endswith('.py') else _js_imports_for_file(full_path)
            source_id = f'{_node_type_for_kind(kind).value}:{rel_path}'
            for imported in imports:
                if not imported:
                    continue
                import_name = imported.strip().strip('"\'')
                if import_name.startswith(('http://', 'https://')):
                    continue
                if import_name.startswith('.') or import_name.startswith('/'):
                    target_rel = _resolve_internal_import(root_dir, rel_path, import_name, repo_files)
                    if target_rel is None:
                        continue
                    target_kind = classify_file(target_rel)
                    if target_kind == ArtifactKind.OTHER:
                        continue
                    target_id = f'{_node_type_for_kind(target_kind).value}:{target_rel}'
                    if target_id not in node_map:
                        continue
                    evidence = (
                        RepositoryGraphEvidence(
                            artifact=rel_path,
                            description=f"Static import evidence in {rel_path} resolves to {target_rel}.",
                            evidence_type='static_analysis',
                        ),
                    )
                    add_edge(source_id, target_id, RepositoryRelationshipType.IMPORTS, f'{rel_path} imports {target_rel}.', evidence)
                    add_edge(target_id, source_id, RepositoryRelationshipType.IMPORTED_BY, f'{target_rel} is imported by {rel_path}.', evidence)
                    continue

                dependency_id = f'dependency:{import_name}'
                if dependency_id not in node_map:
                    add_node(
                        RepositoryGraphNode(
                            id=dependency_id,
                            label=import_name,
                            node_type=RepositoryNodeType.DEPENDENCY,
                            description='External dependency discovered from a static import reference.',
                            metadata={'name': import_name, 'kind': 'dependency'},
                        )
                    )
                evidence = (
                    RepositoryGraphEvidence(
                        artifact=rel_path,
                        description=f"Static import evidence indicates {rel_path} depends on {import_name}.",
                        evidence_type='static_analysis',
                    ),
                )
                add_edge(source_id, dependency_id, RepositoryRelationshipType.DEPENDS_ON, f'{rel_path} depends on {import_name}.', evidence)

        for dep_name in sorted(_dependency_manifest_names(root_dir)):
            dep_id = f'dependency:{dep_name}'
            if dep_id not in node_map:
                add_node(
                    RepositoryGraphNode(
                        id=dep_id,
                        label=dep_name,
                        node_type=RepositoryNodeType.DEPENDENCY,
                        description='Dependency declared in a repository manifest.',
                        metadata={'name': dep_name, 'kind': 'dependency'},
                    )
                )
            add_edge(repo_root_id, dep_id, RepositoryRelationshipType.DEPENDS_ON, f'Repository depends on {dep_name}.', ())

        for rel_path in sorted(repo_files):
            if classify_file(rel_path) == ArtifactKind.CONFIGURATION:
                config_id = f'{RepositoryNodeType.CONFIGURATION.value}:{rel_path}'
                if config_id in node_map:
                    add_edge(repo_root_id, config_id, RepositoryRelationshipType.CONFIGURED_BY, f'Repository uses {rel_path} as configuration.', ())
            if classify_file(rel_path) == ArtifactKind.DOCUMENTATION:
                doc_id = f'{RepositoryNodeType.DOCUMENTATION.value}:{rel_path}'
                if doc_id in node_map:
                    add_edge(repo_root_id, doc_id, RepositoryRelationshipType.DOCUMENTED_BY, f'Repository is documented by {rel_path}.', ())

        for rel_path in sorted(repo_files):
            if classify_file(rel_path) != ArtifactKind.TEST:
                continue
            test_id = f'{RepositoryNodeType.TEST.value}:{rel_path}'
            test_stem = Path(rel_path).stem.lower()
            for candidate in sorted(repo_files):
                if classify_file(candidate) != ArtifactKind.SOURCE:
                    continue
                if candidate == rel_path:
                    continue
                source_stem = Path(candidate).stem.lower()
                if source_stem in test_stem or test_stem in source_stem or test_stem.replace('test_', '') == source_stem:
                    source_id = f'{RepositoryNodeType.SOURCE.value}:{candidate}'
                    if source_id in node_map and test_id in node_map:
                        evidence = (
                            RepositoryGraphEvidence(
                                artifact=rel_path,
                                description=f"Test file {rel_path} shares naming evidence with {candidate}.",
                                evidence_type='name_similarity',
                            ),
                        )
                        add_edge(source_id, test_id, RepositoryRelationshipType.TESTED_BY, f'{candidate} is tested by {rel_path}.', evidence)

        graph.nodes = sorted(node_map.values(), key=lambda node: (node.node_type.value, node.label.lower()))
        graph.edges = sorted(edge_map.values(), key=lambda edge: (edge.relationship.value, edge.source, edge.target))
        graph.generated_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    finally:
        if cleanup_required and retrieved is not None:
            retrieved.cleanup()

    return graph


def serialize_repository_knowledge_graph(graph: RepositoryKnowledgeGraph, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    return target


def write_repository_graph_payload(graph: RepositoryKnowledgeGraph, *, frontend_dir: str | Path | None = None) -> Path:
    repo_root = Path(frontend_dir) if frontend_dir is not None else Path(__file__).resolve().parents[2]
    frontend_root = repo_root / 'frontend'
    target = frontend_root / 'public' / 'devflow-graph.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    return serialize_repository_knowledge_graph(graph, target)

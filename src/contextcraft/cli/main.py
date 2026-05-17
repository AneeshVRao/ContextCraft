"""ContextCraft CLI — Typer application.

Commands:
    contextcraft index <repo_path>   Index a codebase
    contextcraft ask "question"      Ask a question about indexed code
    contextcraft status              Show indexed repositories
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pathspec
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from contextcraft.config import settings
from contextcraft.db import chunks_repo
from contextcraft.db.connection import close_pool, run_migrations
from contextcraft.embeddings.openai import OpenAIEmbedder
from contextcraft.git.blame import get_chunk_blame, get_file_blame
from contextcraft.git.history import get_file_history
from contextcraft.llm.base import BaseLLM
from contextcraft.models import (
    CodeChunk,
    Language,
    SearchResult,
)
from contextcraft.parser.ast_parser import detect_language, parse_file
from contextcraft.search.context_builder import build_context, format_sources
from contextcraft.search.hybrid import hybrid_search

app = typer.Typer(
    name="contextcraft",
    help="Index any codebase and ask questions with full file + git-history context.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_files(repo_path: Path) -> list[Path]:
    """Walk *repo_path*, skip ignored patterns, return supported files."""
    # Load .gitignore patterns
    gitignore_path = repo_path / ".gitignore"
    contextignore_path = repo_path / ".contextignore"
    patterns = list(settings.default_ignore_patterns)

    for ignore_file in (gitignore_path, contextignore_path):
        if ignore_file.is_file():
            patterns.extend(
                line.strip()
                for line in ignore_file.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            )

    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    files: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(repo_path)
        except ValueError:
            continue
        rel_str = str(rel).replace("\\", "/")
        if spec.match_file(rel_str):
            continue
        if detect_language(path) is not None:
            files.append(path)

    return sorted(files)


def _get_changed_files(repo_path: Path, last_commit: str | None) -> set[str] | None:
    """Return set of files changed since *last_commit*, or None for full index."""
    if not last_commit:
        return None
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", last_commit, "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return {f.strip() for f in result.stdout.splitlines() if f.strip()}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _get_head_commit(repo_path: Path) -> str | None:
    """Return the current HEAD commit hash."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


LLM_SYSTEM_PROMPT = """You are ContextCraft, an expert code analysis assistant.
You answer questions about codebases using the provided code context.

Rules:
- Base your answers ONLY on the provided code context
- Reference specific file paths and line numbers when explaining code
- If the context doesn't contain enough information, say so clearly
- Be concise but thorough
- Use markdown formatting for code references

The code context below includes:
- File paths with line numbers
- Git blame information (who last modified each section)
- The actual source code
"""


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def index(
    repo_path: str = typer.Argument(..., help="Path to the repository to index"),
    incremental: bool = typer.Option(
        False, "--incremental", "-i", help="Only re-index files changed since last index"
    ),
    skip_embeddings: bool = typer.Option(
        False, "--skip-embeddings", help="Parse and store chunks without computing embeddings"
    ),
    skip_git: bool = typer.Option(False, "--skip-git", help="Skip git blame and history"),
) -> None:
    """Index a codebase: parse → git blame → embed → store."""
    asyncio.run(_index_async(Path(repo_path).resolve(), incremental, skip_embeddings, skip_git))


async def _index_async(
    repo_path: Path,
    incremental: bool,
    skip_embeddings: bool,
    skip_git: bool,
) -> None:
    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] {repo_path} is not a directory")
        raise typer.Exit(1)

    console.print(f"\n[bold blue]ContextCraft[/bold blue] — Indexing [cyan]{repo_path}[/cyan]\n")

    # --- DB setup ---
    await run_migrations()

    # --- Repository record ---
    head_commit = _get_head_commit(repo_path)
    repo = await chunks_repo.get_repository_by_path(str(repo_path))

    # --- Determine files to process ---
    all_files = _collect_files(repo_path)
    files_to_process = all_files

    if incremental and repo and repo.last_commit_hash:
        changed = _get_changed_files(repo_path, repo.last_commit_hash)
        if changed is not None:
            files_to_process = [
                f for f in all_files if str(f.relative_to(repo_path)).replace("\\", "/") in changed
            ]
            console.print(
                f"  [dim]Incremental mode: {len(files_to_process)}/{len(all_files)} files changed[/dim]"
            )
        else:
            console.print("  [yellow]Could not determine changed files — full re-index[/yellow]")

    if not files_to_process:
        console.print("  [green]No files to process — index is up to date[/green]")
        await close_pool()
        return

    # Detect languages
    languages_seen: set[Language] = set()
    for f in files_to_process:
        lang = detect_language(f)
        if lang:
            languages_seen.add(lang)

    # Upsert repository
    repo_record = await chunks_repo.upsert_repository(
        name=repo_path.name,
        local_path=str(repo_path),
        languages=list(languages_seen),
        last_commit_hash=head_commit,
    )
    repo_id = repo_record.id

    # --- Parse files ---
    all_chunks: list[CodeChunk] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        parse_task = progress.add_task("Parsing files…", total=len(files_to_process))

        for file_path in files_to_process:
            rel_path = str(file_path.relative_to(repo_path)).replace("\\", "/")

            # Delete old chunks for this file (Pitfall 7)
            await chunks_repo.delete_chunks_by_file(repo_id, rel_path)

            chunks = parse_file(file_path, repo_root=repo_path)
            for chunk in chunks:
                chunk.repo_id = repo_id

            # Attach git context
            if not skip_git and (repo_path / ".git").is_dir():
                file_blame = get_file_blame(repo_path, rel_path)
                file_hist = get_file_history(repo_path, rel_path)
                for chunk in chunks:
                    chunk.git_blame = get_chunk_blame(file_blame, chunk.start_line, chunk.end_line)
                    chunk.commit_history = file_hist

            all_chunks.extend(chunks)
            progress.advance(parse_task)

    console.print(
        f"  Parsed [bold]{len(all_chunks)}[/bold] chunks from {len(files_to_process)} files"
    )

    # --- Embed ---
    if not skip_embeddings and settings.openai_api_key:
        console.print("  Embedding chunks…")
        embedder = OpenAIEmbedder()
        texts = [c.content for c in all_chunks]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            embed_task = progress.add_task("Embedding…", total=len(texts))

            # Process in batches
            batch_size = settings.embedding_batch_size
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                embeddings = await embedder.embed(batch)
                for j, emb in enumerate(embeddings):
                    all_chunks[i + j].embedding = emb
                progress.advance(embed_task, len(batch))

        console.print(f"  [green]✓[/green] Embedded {len(all_chunks)} chunks")
    elif skip_embeddings:
        console.print("  [dim]Skipping embeddings (--skip-embeddings)[/dim]")
    else:
        console.print(
            "  [yellow]⚠ No OPENAI_API_KEY set — skipping embeddings.[/yellow]\n"
            "  Set CONTEXTCRAFT_OPENAI_API_KEY to enable vector search."
        )

    # --- Store ---
    await chunks_repo.insert_chunks(all_chunks)
    count = await chunks_repo.update_chunk_count(repo_id)

    # --- Create HNSW index (Pitfall 3: after bulk insert) ---
    if not skip_embeddings and settings.openai_api_key:
        try:
            await chunks_repo.create_hnsw_index()
            console.print("  [green]✓[/green] HNSW vector index created")
        except Exception as e:
            console.print(f"  [yellow]⚠ HNSW index creation skipped: {e}[/yellow]")

    # --- Resolve dependency graph ---
    try:
        from contextcraft.db.graph_repo import insert_edges, run_graph_migration
        from contextcraft.graph.resolver import build_chunk_registry, resolve_all

        await run_graph_migration()
        registry = build_chunk_registry(all_chunks)
        edges = resolve_all(all_chunks, registry)
        if edges:
            await insert_edges(edges)
            console.print(
                f"  [green]✓[/green] Resolved {len(edges)} dependency edges "
                f"({sum(1 for e in edges if e.edge_type == 'imports')} imports, "
                f"{sum(1 for e in edges if e.edge_type == 'inherits')} inherits)"
            )
        else:
            console.print("  [dim]No internal dependency edges found[/dim]")
    except Exception as e:
        console.print(f"  [yellow]⚠ Dependency graph skipped: {e}[/yellow]")

    console.print(
        f"\n  [bold green]Done![/bold green] Indexed {count} chunks from "
        f"[cyan]{repo_path.name}[/cyan]\n"
    )

    await close_pool()


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to ask about the codebase"),
    repo: str = typer.Option(
        None, "--repo", "-r", help="Repository path or name to scope the query"
    ),
    top_k: int = typer.Option(None, "--top-k", "-k", help="Number of code chunks to retrieve"),
    no_rerank: bool = typer.Option(
        False, "--no-rerank", help="Disable Cohere reranker and use pure RRF ranking"
    ),
    with_deps: bool = typer.Option(
        False, "--with-deps", help="Expand context with 1-hop dependency chunks"
    ),
) -> None:
    """Ask a question about an indexed codebase."""
    asyncio.run(_ask_async(question, repo, top_k, no_rerank, with_deps))


async def _ask_async(
    question: str, repo: str | None, top_k: int | None, no_rerank: bool, with_deps: bool
) -> None:
    top_k = top_k or settings.search_top_k

    await run_migrations()

    # Find the repository
    repos = await chunks_repo.list_repositories()
    if not repos:
        console.print(
            "[red]No repositories indexed yet.[/red] Run `contextcraft index <path>` first."
        )
        await close_pool()
        raise typer.Exit(1)

    target_repo = None
    if repo:
        for r in repos:
            if r.name == repo or r.local_path == repo or str(r.id) == repo:
                target_repo = r
                break
        if not target_repo:
            console.print(f"[red]Repository '{repo}' not found.[/red]")
            await close_pool()
            raise typer.Exit(1)
    else:
        target_repo = repos[0]
        if len(repos) > 1:
            console.print(
                f"[dim]Multiple repos indexed — using '{target_repo.name}'. "
                f"Use --repo to specify.[/dim]"
            )

    console.print(
        f"\n[bold blue]ContextCraft[/bold blue] — "
        f"Searching [cyan]{target_repo.name}[/cyan] ({target_repo.chunk_count} chunks)\n"
    )

    # Embed the question
    if not settings.openai_api_key:
        console.print("[red]CONTEXTCRAFT_OPENAI_API_KEY is required for search.[/red]")
        await close_pool()
        raise typer.Exit(1)

    embedder = OpenAIEmbedder()
    with console.status("Embedding query…"):
        query_embedding = await embedder.embed_single(question)

    # Search
    use_reranker = settings.rerank_enabled and not no_rerank and bool(settings.cohere_api_key)
    fetch_k = 20 if use_reranker else top_k

    with console.status("Searching…"):
        results = await hybrid_search(
            query_embedding=query_embedding,
            query_text=question,
            repo_id=target_repo.id,
            top_k=fetch_k,
        )

    if not results:
        console.print("[yellow]No relevant code found.[/yellow]")
        await close_pool()
        return

    # Rerank
    if use_reranker:
        with console.status("Reranking…"):
            from contextcraft.reranker.cohere import CohereReranker

            reranker = CohereReranker()
            results = await reranker.rerank(question, results, top_k)

    # Expand with dependency chunks if requested
    dep_results: list[SearchResult] | None = None
    if with_deps:
        try:
            from contextcraft.graph.expander import expand_with_deps

            chunk_ids = [sr.chunk.id for sr in results]
            dep_chunks = await expand_with_deps(chunk_ids)
            if dep_chunks:
                dep_results = [
                    SearchResult(chunk=dc, score=0.0, rank=len(results) + i)
                    for i, dc in enumerate(dep_chunks)
                ]
                console.print(
                    f"  [dim]Expanded context with {len(dep_chunks)} dependency chunks[/dim]"
                )
        except Exception as e:
            console.print(f"  [yellow]⚠ Dependency expansion skipped: {e}[/yellow]")

    # Build context
    context = build_context(
        results,
        repo_path=target_repo.local_path,
        expand_deps=with_deps,
        dep_chunks=dep_results,
    )

    # Build prompt
    user_message = f"## Code Context\n\n{context}\n\n## Question\n\n{question}"

    # Get LLM provider
    llm = _get_llm()

    # Stream response
    console.print("[bold]Answer:[/bold]\n")
    full_response = ""

    try:
        async for token in llm.stream(LLM_SYSTEM_PROMPT, user_message):
            console.print(token, end="", highlight=False)
            full_response += token
    except Exception as e:
        console.print(f"\n[red]LLM error: {e}[/red]")

    # Print sources (verified metadata, not from LLM — Pitfall 8)
    console.print("\n")
    sources = format_sources(results)
    console.print(f"[dim]{sources}[/dim]")
    console.print()

    await close_pool()


@app.command()
def status() -> None:
    """Show indexed repositories and their stats."""
    asyncio.run(_status_async())


async def _status_async() -> None:
    await run_migrations()

    repos = await chunks_repo.list_repositories()

    if not repos:
        console.print("[dim]No repositories indexed yet.[/dim]")
        await close_pool()
        return

    table = Table(title="ContextCraft — Indexed Repositories", show_lines=True)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Path", style="dim")
    table.add_column("Languages", style="green")
    table.add_column("Chunks", justify="right", style="bold")
    table.add_column("Last Indexed", style="yellow")
    table.add_column("Last Commit", style="dim", max_width=12)

    for repo in repos:
        langs = ", ".join(lang.value for lang in repo.languages)
        indexed = repo.last_indexed_at.strftime("%Y-%m-%d %H:%M") if repo.last_indexed_at else "—"
        table.add_row(
            repo.name,
            repo.local_path,
            langs,
            str(repo.chunk_count),
            indexed,
            (repo.last_commit_hash or "—")[:12],
        )

    console.print(table)
    await close_pool()


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _get_llm() -> BaseLLM:
    """Return the configured LLM provider."""
    if settings.llm_provider == "anthropic":
        from contextcraft.llm.anthropic import AnthropicLLM

        return AnthropicLLM()
    elif settings.llm_provider == "ollama":
        from contextcraft.llm.ollama import OllamaLLM

        return OllamaLLM()
    else:
        from contextcraft.llm.openai import OpenAILLM

        return OpenAILLM()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()

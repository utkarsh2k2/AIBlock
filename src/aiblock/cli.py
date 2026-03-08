"""CLI entry point for AIBlock."""

import json
from pathlib import Path

import click

from aiblock.config import Config
from aiblock.pipeline import build_pipeline

_DEFAULT_CONFIG = Path(__file__).parents[3] / "config.yaml"


@click.group()
def main():
    """AIBlock — detect AI-generated audio from YouTube and Spotify."""


@main.command()
@click.argument("url")
@click.option(
    "--platform", "-p",
    required=True,
    type=click.Choice(["youtube", "spotify"], case_sensitive=False),
    help="Source platform.",
)
@click.option(
    "--config", "-c",
    default=str(_DEFAULT_CONFIG),
    show_default=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to config.yaml.",
)
@click.option("--json-output", is_flag=True, help="Print result as JSON.")
def detect(url: str, platform: str, config: Path, json_output: bool):
    """Detect whether audio at URL is AI-generated."""
    cfg = Config.from_yaml(config)
    pipeline = build_pipeline(platform.lower(), cfg)

    click.echo(f"Fetching audio from {platform.upper()}...")
    result = pipeline.run(url)

    if json_output:
        click.echo(json.dumps(result, indent=2))
    else:
        verdict = result["verdict"]
        score = result["score"]
        confidence = result["confidence"]
        chunks = result["chunks"]
        color = "red" if verdict == "AI" else "green"
        click.echo(
            f"\nVerdict:    {click.style(verdict, fg=color, bold=True)}\n"
            f"Score:      {score:.2%} AI probability\n"
            f"Confidence: {confidence:.2%}\n"
            f"Chunks:     {chunks} x {cfg.preprocess.chunk_sec}s"
        )

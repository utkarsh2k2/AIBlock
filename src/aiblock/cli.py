"""CLI entry point for AIBlock."""

import json
from pathlib import Path

import click

from aiblock.config import Config, DetectorConfig
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
@click.option(
    "--model", is_flag=True, default=False,
    help="Enable wav2vec2 deepfake model (~350 MB download on first run). "
         "Slower but more accurate than the default spectral-only analysis.",
)
def detect(url: str, platform: str, config: Path, json_output: bool, model: bool):
    """Detect whether audio at URL is AI-generated."""
    cfg = Config.from_yaml(config)

    if model:
        cfg.detectors["wav2vec2"] = DetectorConfig(
            model_id="Zeyadd-Mostaffa/Deepfake-Audio-Detection-v1",
            device="cpu",
            weight=3.0,  # 75 % effective weight alongside spectral (weight 1.0)
        )

    pipeline = build_pipeline(platform.lower(), cfg)

    click.echo(f"Fetching audio from {platform.upper()}...")
    if model:
        click.echo("Loading wav2vec2 model (first run downloads ~350 MB)...")

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


@main.command("serve")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--workers", default=1, show_default=True)
def serve(host: str, port: int, workers: int):
    """Start the AIBlock REST API server."""
    try:
        import uvicorn
    except ImportError:
        raise click.ClickException("uvicorn is required: pip install 'aiblock[api]'")

    uvicorn.run(
        "aiblock.api.app:create_app",
        host=host,
        port=port,
        workers=workers,
        factory=True,
    )

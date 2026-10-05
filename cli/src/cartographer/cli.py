"""Typer app entry point: wires the `cartographer` subcommands together."""

from __future__ import annotations

import typer

from cartographer.commands import detect, doctor, gc, init, promote, recall, seed, serve
from cartographer.commands import hook as hook_cmd
from cartographer.commands import stack as stack_cmd
from cartographer.commands import ui_cmd

def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version
        typer.echo(f"cartographer {version('cartographer')}")
        raise typer.Exit()


app = typer.Typer(
    name="cartographer",
    help="Persistent knowledge layer CLI for Claude Code projects.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _main(
    version: bool = typer.Option(  # noqa: ARG001
        False, "--version", callback=_version_callback, is_eager=True, help="Show version."
    ),
) -> None:
    pass

app.command("detect")(detect.run)
app.command("init")(init.run)
app.add_typer(stack_cmd.app, name="stack")
app.add_typer(hook_cmd.app, name="hook")
app.command("seed")(seed.run)
app.command("promote")(promote.run)
app.command("recall")(recall.run)
app.command("ui")(ui_cmd.run)
app.command("doctor")(doctor.run)
app.add_typer(serve.app, name="serve")
app.command("gc")(gc.run)


if __name__ == "__main__":
    app()

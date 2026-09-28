"""Typer app entry point: wires the `cartographer` subcommands together."""

from __future__ import annotations

import typer

from cartographer.commands import detect, doctor, init, promote, recall, seed
from cartographer.commands import hook as hook_cmd
from cartographer.commands import stack as stack_cmd
from cartographer.commands import ui_cmd

app = typer.Typer(
    name="cartographer",
    help="Persistent knowledge layer CLI for Claude Code projects.",
    no_args_is_help=True,
    add_completion=False,
)

app.command("detect")(detect.run)
app.command("init")(init.run)
app.add_typer(stack_cmd.app, name="stack")
app.add_typer(hook_cmd.app, name="hook")
app.command("seed")(seed.run)
app.command("promote")(promote.run)
app.command("recall")(recall.run)
app.command("ui")(ui_cmd.run)
app.command("doctor")(doctor.run)


if __name__ == "__main__":
    app()

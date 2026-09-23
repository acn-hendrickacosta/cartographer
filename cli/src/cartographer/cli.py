"""Typer app entry point: wires the six `cartographer` subcommands together."""

from __future__ import annotations

import typer

from cartographer.commands import detect, doctor, init, promote, recall
from cartographer.commands import stack as stack_cmd

app = typer.Typer(
    name="cartographer",
    help="Persistent knowledge layer CLI for Claude Code projects.",
    no_args_is_help=True,
    add_completion=False,
)

app.command("detect")(detect.run)
app.command("init")(init.run)
app.add_typer(stack_cmd.app, name="stack")
app.command("promote")(promote.run)
app.command("recall")(recall.run)
app.command("doctor")(doctor.run)


if __name__ == "__main__":
    app()

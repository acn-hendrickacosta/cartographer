# Python: Type hints

- Add type hints on all public function and method signatures (parameters and return type). Internal helpers should have hints too unless the types are genuinely obvious from a two-line read.
- Use `from __future__ import annotations` at the top of every module so forward references work without string quoting and annotations are not evaluated at runtime.
- Prefer built-in types over typing module aliases where available: `list[str]` not `List[str]`, `dict[str, int]` not `Dict[str, int]`, `tuple[int, ...]` not `Tuple[int, ...]`.
- Use `X | None` instead of `Optional[X]`. Use `X | Y` instead of `Union[X, Y]`.
- Use `TypeAlias` when a type alias is non-obvious: `Scope: TypeAlias = Literal["local", "global"]`.
- Mark data classes and config objects with `@dataclass` or Pydantic `BaseModel`. Do not use plain dicts for structured data that is passed across function boundaries; the type is unverifiable and the fields are undocumented.
- Run `mypy` or `pyright` in strict mode on the public API surface. Internal modules may use `# type: ignore` sparingly for genuine edge cases with a brief explanation.

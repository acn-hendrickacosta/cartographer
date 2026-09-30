# Python: Patterns and idioms

- Write readable code first. Function names should read as verbs, variable names as nouns. Prefer clarity over cleverness; the next reader is usually you six months later.
- Prefer EAFP (Easier to Ask Forgiveness than Permission) over LBYL (Look Before You Leap). Use `try/except` for conditions that are genuinely exceptional, not `try/except` as a substitute for an `if` check on normal flow.
- Use `with` statements for all resource management — files, connections, locks, transactions. Write custom context managers with `@contextlib.contextmanager` for setup/teardown that does not fit in a class.
- Use list comprehensions for simple, single-condition transformations. Use generator expressions (`sum(x**2 for x in items)`) when the result does not need to be held in memory. When the logic requires two or more conditions or transformations, write a named generator function instead — comprehensions should not need comments to understand.
- Use generator functions (`yield`) to iterate over large datasets or streams. Never load an entire file or query result set into a list when line-by-line or batch processing suffices.
- Use `@dataclass` for structured data passed across function boundaries. Plain dicts are unverifiable and undocumented. Add `frozen=True` for value objects that should not change after construction. Use `field(default_factory=list)` rather than a mutable default.
- Use `typing.Protocol` for structural interfaces (duck typing). This avoids forcing inheritance and works with any object that has the right methods. Define a protocol where you need to describe a contract, not where you want to reuse code.
- Use `typing.NamedTuple` for simple immutable records. It is lighter than a full dataclass and supports positional unpacking.
- Use `functools.wraps` inside every decorator to preserve the wrapped function's `__name__`, `__doc__`, and signature. Without it, debugging and introspection break.
- Use `Enum` for named constants instead of magic numbers or strings. An `Enum` communicates the full set of valid values and prevents typos.
- Use `pathlib.Path` for all filesystem operations. Avoid `os.path.join` string concatenation; `Path` operators and methods are clearer and cross-platform.
- Use `"".join(...)` to build strings in a loop. String concatenation with `+=` is O(n²) due to immutability; a single `join` over a list is O(n).
- Use `__slots__` in classes instantiated at very high volume to reduce per-instance memory. This is a targeted optimization; do not add it by default.
- Control what a package exports by setting `__all__` in `__init__.py`. Explicit exports make the public API clear and prevent accidental re-export of internal symbols.
- Keep import order: standard library, then third-party, then local. Enforce this with `isort` or `ruff`. Never use `from module import *`; it pollutes the namespace and makes dependencies invisible.

## Anti-patterns to avoid

- Never use a mutable object as a default argument: `def f(x=[])` shares the list across all calls. Use `def f(x=None)` and create the mutable object inside the function.
- Use `isinstance(obj, SomeType)` not `type(obj) == SomeType`. `isinstance` respects inheritance and is the idiomatic check.
- Compare to `None` with `is` / `is not`, not `==`. `value == None` can be overridden; `value is None` cannot.
- Do not shadow built-in names (`list`, `dict`, `str`, `id`, `type`) as local variables.

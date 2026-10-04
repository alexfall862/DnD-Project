"""Safe expression language for derived statistics and conditions (rules-engine §4).

Two equivalent forms are accepted:

* a compact infix string — `"10 + attr.might * 2"`, `"clamp(skill.stealth + 1, 0, 5)"`,
  `"if(attr.agility > 5, 1, 0)"`;
* a JSON AST — `{"op": "add", "args": [10, {"op": "mul", "args": [{"ref": "attr.might"}, 2]}]}`.

Both compile to the same `Expr` tree and are evaluated by `evaluate()` with a resolver that maps
reference names to values. There is no `eval`, no attribute access, no calls other than the
whitelisted functions, and no way to reach Python objects from a ruleset.

Whitelisted: + - * / (true division) // (floor division) % , comparisons, `and` `or` `not`,
unary minus, and the functions min max clamp floor ceil round abs if.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Number = int | float
Value = Number | bool


class ExpressionError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Lit:
    value: Value


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class Op:
    op: str
    args: tuple[Expr, ...]


Expr = Lit | Ref | Op

BINARY = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "div": lambda a, b: a / b,
    "floordiv": lambda a, b: a // b,
    "mod": lambda a, b: a % b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
}
FUNCTIONS: dict[str, tuple[int | None, Callable[..., Value]]] = {
    "min": (None, min),
    "max": (None, max),
    "clamp": (3, lambda x, lo, hi: max(lo, min(hi, x))),
    "floor": (1, math.floor),
    "ceil": (1, math.ceil),
    "round": (1, lambda x: int(round(x))),
    "abs": (1, abs),
}
ARITY = {name: n for name, (n, _) in FUNCTIONS.items()}

INFIX_TO_OP = {
    "+": "add",
    "-": "sub",
    "*": "mul",
    "/": "div",
    "//": "floordiv",
    "%": "mod",
    "==": "eq",
    "!=": "ne",
    "<": "lt",
    "<=": "le",
    ">": "gt",
    ">=": "ge",
}

REF_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9][a-z0-9_]*)+$")  # no _-led segments

# ---------------------------------------------------------------------------------------------
# JSON AST -> Expr
# ---------------------------------------------------------------------------------------------


def from_json(node: Any) -> Expr:
    if isinstance(node, bool):
        return Lit(node)
    if isinstance(node, int | float):
        return Lit(node)
    if isinstance(node, str):
        return parse(node)
    if isinstance(node, dict):
        if "ref" in node and len(node) == 1:
            name = node["ref"]
            if not isinstance(name, str) or not REF_PATTERN.match(name):
                raise ExpressionError(f"bad reference {name!r}")
            return Ref(name)
        if "op" in node:
            op = node["op"]
            args = node.get("args", [])
            if not isinstance(args, list):
                raise ExpressionError("args must be a list")
            return _check_op(Op(op, tuple(from_json(a) for a in args)))
    raise ExpressionError(f"unsupported expression node {node!r}")


def _check_op(node: Op) -> Op:
    op, n = node.op, len(node.args)
    if op in BINARY:
        if n != 2:
            raise ExpressionError(f"{op} takes 2 args, got {n}")
    elif op in ("and", "or"):
        if n < 2:
            raise ExpressionError(f"{op} takes at least 2 args")
    elif op in ("not", "neg"):
        if n != 1:
            raise ExpressionError(f"{op} takes 1 arg")
    elif op == "if":
        if n != 3:
            raise ExpressionError("if takes 3 args")
    elif op in FUNCTIONS:
        arity = ARITY[op]
        if arity is None and n < 1 or arity is not None and n != arity:
            raise ExpressionError(f"{op} takes {arity or 'at least 1'} args, got {n}")
    else:
        raise ExpressionError(f"unknown operation {op!r}")
    return node


# ---------------------------------------------------------------------------------------------
# Infix parser (recursive descent)
# ---------------------------------------------------------------------------------------------

TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_.]*)|(?P<op>//|==|!=|<=|>=|[-+*/%<>(),]))"
)


def _tokenize(text: str) -> list[tuple[str, str]]:
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ExpressionError(f"unexpected character at {pos}: {text[pos : pos + 10]!r}")
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))  # type: ignore[arg-type]
    return out


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.t = tokens
        self.i = 0

    def peek(self) -> tuple[str, str] | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, value: str | None = None) -> tuple[str, str]:
        tok = self.peek()
        if tok is None or (value is not None and tok[1] != value):
            raise ExpressionError(f"expected {value!r}, got {tok!r}")
        self.i += 1
        return tok

    def parse(self) -> Expr:
        e = self.or_()
        if self.peek() is not None:
            raise ExpressionError(f"trailing tokens: {self.t[self.i :]}")
        return e

    def or_(self) -> Expr:
        e = self.and_()
        while self.peek() == ("name", "or"):
            self.take()
            e = Op("or", (e, self.and_()))
        return e

    def and_(self) -> Expr:
        e = self.not_()
        while self.peek() == ("name", "and"):
            self.take()
            e = Op("and", (e, self.not_()))
        return e

    def not_(self) -> Expr:
        if self.peek() == ("name", "not"):
            self.take()
            return Op("not", (self.not_(),))
        return self.comparison()

    def comparison(self) -> Expr:
        e = self.additive()
        tok = self.peek()
        if tok and tok[0] == "op" and tok[1] in ("==", "!=", "<", "<=", ">", ">="):
            self.take()
            e = Op(INFIX_TO_OP[tok[1]], (e, self.additive()))
        return e

    def additive(self) -> Expr:
        e = self.term()
        while (tok := self.peek()) and tok[0] == "op" and tok[1] in ("+", "-"):
            self.take()
            e = Op(INFIX_TO_OP[tok[1]], (e, self.term()))
        return e

    def term(self) -> Expr:
        e = self.unary()
        while (tok := self.peek()) and tok[0] == "op" and tok[1] in ("*", "/", "//", "%"):
            self.take()
            e = Op(INFIX_TO_OP[tok[1]], (e, self.unary()))
        return e

    def unary(self) -> Expr:
        if self.peek() == ("op", "-"):
            self.take()
            return Op("neg", (self.unary(),))
        return self.primary()

    def primary(self) -> Expr:
        tok = self.take()
        kind, text = tok
        if kind == "num":
            return Lit(float(text) if "." in text else int(text))
        if kind == "op" and text == "(":
            e = self.or_()
            self.take(")")
            return e
        if kind == "name":
            if text in ("true", "false"):
                return Lit(text == "true")
            if self.peek() == ("op", "("):
                self.take("(")
                args: list[Expr] = []
                if self.peek() != ("op", ")"):
                    args.append(self.or_())
                    while self.peek() == ("op", ","):
                        self.take()
                        args.append(self.or_())
                self.take(")")
                if text == "if":
                    return _check_op(Op("if", tuple(args)))
                if text not in FUNCTIONS:
                    raise ExpressionError(f"unknown function {text!r}")
                return _check_op(Op(text, tuple(args)))
            if not REF_PATTERN.match(text):
                raise ExpressionError(f"bad reference {text!r} (use dotted names like attr.might)")
            return Ref(text)
        raise ExpressionError(f"unexpected token {tok!r}")


def parse(text: str) -> Expr:
    if not isinstance(text, str) or not text.strip():
        raise ExpressionError("empty expression")
    return _Parser(_tokenize(text)).parse()


def compile_expr(source: str | int | float | bool | dict[str, Any]) -> Expr:
    """Accept infix text, a literal, or a JSON AST."""
    return from_json(source)


# ---------------------------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------------------------

Resolver = Callable[[str], Value]


def references(expr: Expr) -> set[str]:
    if isinstance(expr, Ref):
        return {expr.name}
    if isinstance(expr, Op):
        out: set[str] = set()
        for a in expr.args:
            out |= references(a)
        return out
    return set()


def evaluate(expr: Expr, resolve: Resolver) -> Value:
    if isinstance(expr, Lit):
        return expr.value
    if isinstance(expr, Ref):
        try:
            v = resolve(expr.name)
        except KeyError as exc:
            raise ExpressionError(f"unresolved reference {expr.name!r}") from exc
        if not isinstance(v, int | float | bool):
            raise ExpressionError(f"reference {expr.name!r} is not numeric/boolean")
        return v
    op = expr.op
    if op == "if":
        cond = evaluate(expr.args[0], resolve)
        return evaluate(expr.args[1] if cond else expr.args[2], resolve)
    if op == "and":
        return all(evaluate(a, resolve) for a in expr.args)
    if op == "or":
        return any(evaluate(a, resolve) for a in expr.args)
    if op == "not":
        return not evaluate(expr.args[0], resolve)
    if op == "neg":
        return -evaluate(expr.args[0], resolve)  # type: ignore[operator]
    vals = [evaluate(a, resolve) for a in expr.args]
    if op in BINARY:
        try:
            return BINARY[op](vals[0], vals[1])
        except ZeroDivisionError as exc:
            raise ExpressionError("division by zero") from exc
    _, fn = FUNCTIONS[op]
    return fn(*vals)


def evaluate_int(expr: Expr, resolve: Resolver) -> int:
    v = evaluate(expr, resolve)
    if isinstance(v, bool):
        return int(v)
    return math.floor(v) if isinstance(v, float) else v

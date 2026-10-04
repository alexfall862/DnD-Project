"""Safe expression evaluator: parsing, evaluation, and refusal of anything unsafe."""

from __future__ import annotations

import pytest

from app.engine.expressions import (
    ExpressionError,
    Lit,
    Op,
    Ref,
    compile_expr,
    evaluate,
    evaluate_int,
    parse,
    references,
)

pytestmark = [pytest.mark.unit, pytest.mark.rules]

CTX = {"attr.might": 5, "attr.agility": 7, "skill.stealth": 2, "flag.armored": True}


def ev(src, ctx=CTX):
    return evaluate(compile_expr(src), lambda n: ctx[n])


@pytest.mark.parametrize(
    "src, expected",
    [
        ("10 + attr.might * 2", 20),
        ("5 + attr.might + attr.agility", 17),  # Stamina-style formula
        ("3 + attr.might", 8),
        ("10 + attr.agility", 17),
        ("(attr.might + attr.agility) / 2", 6),
        ("attr.agility // 2", 3),
        ("attr.agility % 4", 3),
        ("-attr.might + 10", 5),
        ("min(attr.agility, 5)", 5),
        ("max(attr.might, attr.agility)", 7),
        ("clamp(skill.stealth + 5, 0, 5)", 5),
        ("floor(7 / 2)", 3),
        ("ceil(7 / 2)", 4),
        ("round(2.5)", 2),
        ("abs(3 - 10)", 7),
        ("if(attr.agility > 5, 1, 0)", 1),
        ("if(attr.might >= 6, 10, 20)", 20),
        ("attr.might == 5 and attr.agility != 5", True),
        ("attr.might > 9 or flag.armored", True),
        ("not flag.armored", False),
        ("true", True),
        ("10 + if(flag.armored, min(attr.agility, 5), attr.agility)", 15),  # heavy-armour cap
    ],
)
def test_infix_evaluates(src, expected):
    assert ev(src) == expected


def test_json_ast_matches_infix():
    ast = {"op": "add", "args": [10, {"op": "mul", "args": [{"ref": "attr.might"}, 2]}]}
    assert compile_expr(ast) == parse("10 + attr.might * 2")
    assert ev(ast) == 20


def test_literals_pass_through():
    assert compile_expr(7) == Lit(7)
    assert compile_expr(True) == Lit(True)
    assert evaluate_int(compile_expr("7 / 2"), lambda n: 0) == 3


def test_references_are_collected():
    assert references(parse("10 + attr.might * skill.stealth")) == {"attr.might", "skill.stealth"}


@pytest.mark.parametrize(
    "src",
    [
        "__import__('os')",
        "attr.might.__class__",
        "open('x')",
        "lambda: 1",
        "attr.might ** 99999",
        "[1,2]",
        "x = 3",
        "attr.might; 1",
        "might",  # bare names are not references
        "unknown(1)",
        "clamp(1, 2)",
        "if(1, 2)",
        "",
        "1 +",
        "(1 + 2",
    ],
)
def test_unsafe_or_malformed_is_rejected(src):
    with pytest.raises(ExpressionError):
        parse(src)


def test_unresolved_reference_and_division_by_zero():
    with pytest.raises(ExpressionError, match="unresolved"):
        ev("attr.nope + 1")
    with pytest.raises(ExpressionError, match="zero"):
        ev("1 / 0")


def test_json_ast_rejects_unknown_ops_and_bad_arity():
    with pytest.raises(ExpressionError):
        compile_expr({"op": "exec", "args": ["x"]})
    with pytest.raises(ExpressionError):
        compile_expr({"op": "add", "args": [1]})
    with pytest.raises(ExpressionError):
        compile_expr({"ref": "not a ref"})
    assert compile_expr({"op": "neg", "args": [1]}) == Op("neg", (Lit(1),))
    assert compile_expr({"ref": "attr.x"}) == Ref("attr.x")

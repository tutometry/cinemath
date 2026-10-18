"""Shared planner helpers."""

from __future__ import annotations

import re
from typing import Any

import sympy as sp

from cinemath.narration.align import BEAT
from cinemath.narration.plain_text import narration_to_speech
from cinemath.narration.speak_math import speak_latex_math, speak_number as _speak_number
from cinemath.plan.schema import PLAN_VERSION
from cinemath.plan.validate import validate_plan

def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6g}"


def _term_tex(coef: float, symbol: str, *, leading: bool = False) -> str:
    if abs(coef) < 1e-12:
        return ""
    mag = _fmt(abs(coef))
    body = symbol if abs(abs(coef) - 1) < 1e-9 else f"{mag}{symbol}"
    if leading:
        return f"-{body}" if coef < 0 else body
    return f" - {body}" if coef < 0 else f" + {body}"


def _equation_tex(lhs: sp.Expr, rhs: sp.Expr) -> str:
    return f"{sp.latex(sp.simplify(lhs))} = {sp.latex(sp.simplify(rhs))}"


def _var_term_tex(coef: sp.Expr, var: sp.Symbol) -> str:
    c = sp.simplify(coef)
    if c == 1:
        return sp.latex(var)
    if c == -1:
        return f"-{sp.latex(var)}"
    return sp.latex(c * var)


def _balanced_op_tex(lhs: sp.Expr, rhs: sp.Expr, delta: sp.Expr) -> str:
    """Show the same additive move on both sides before simplifying."""
    d = sp.simplify(delta)
    if d.is_Number:
        if d > 0:
            return f"{sp.latex(lhs)} + {sp.latex(d)} = {sp.latex(rhs)} + {sp.latex(d)}"
        if d < 0:
            mag = -d
            return f"{sp.latex(lhs)} - {sp.latex(mag)} = {sp.latex(rhs)} - {sp.latex(mag)}"
    vars_in = d.free_symbols
    if len(vars_in) == 1:
        var = next(iter(vars_in))
        coef = sp.simplify(d).coeff(var, 1)
        if coef != 0 and sp.simplify(d - coef * var) == 0:
            if coef > 0:
                term = _var_term_tex(coef, var)
                return f"{sp.latex(lhs)} + {term} = {sp.latex(rhs)} + {term}"
            term = _var_term_tex(-coef, var)
            return f"{sp.latex(lhs)} - {term} = {sp.latex(rhs)} - {term}"
    left = sp.Add(lhs, delta, evaluate=False)
    right = sp.Add(rhs, delta, evaluate=False)
    return f"{sp.latex(left)} = {sp.latex(right)}"


def _speak_linear_side(expr: sp.Expr, variable: str) -> str:
    var = sp.symbols(variable)
    expr = sp.expand(expr)
    coef = sp.simplify(expr.coeff(var, 1))
    rest = sp.simplify(expr - coef * var)
    parts: list[str] = []
    if coef != 0:
        if coef == 1:
            parts.append(variable)
        elif coef == -1:
            parts.append(f"negative {variable}")
        else:
            parts.append(f"{_speak_number(coef)} {variable}")
    if rest != 0:
        if not parts:
            parts.append(_speak_number(rest))
        elif rest > 0:
            parts.append(f"plus {_speak_number(rest)}")
        else:
            parts.append(f"minus {_speak_number(-rest)}")
    return " ".join(parts) if parts else "zero"


def _speak_prose(text: str) -> str:
    """Plain speech, with small integers read as words."""
    spoken = narration_to_speech(text)

    def repl(match: re.Match[str]) -> str:
        return _speak_number(int(match.group(0)))

    return re.sub(r"-?\d+", repl, spoken)


def _speak_math_tex(tex: str) -> str:
    return speak_latex_math(tex)


def _auto_step_speech(step: dict[str, Any]) -> str:
    """Default narration when a planner step omits an explicit ``speech`` field."""
    title = str(step.get("title") or "").strip()
    expl = str(step.get("explanation") or "").strip()
    prose = _speak_prose(expl or title)
    maths = [str(m).strip() for m in (step.get("math") or []) if str(m).strip()]
    cases = step.get("cases") or []
    if cases and not maths:
        return prose
    if not maths:
        return prose
    parts = [prose]
    for line in maths:
        parts.extend([BEAT, _speak_math_tex(line)])
    return " ".join(parts)


def _speak_equation(lhs: sp.Expr, rhs: sp.Expr, variable: str) -> str:
    return f"{_speak_linear_side(lhs, variable)} equals {_speak_linear_side(rhs, variable)}"


def _speak_balanced(lhs: sp.Expr, rhs: sp.Expr, delta: sp.Expr, variable: str) -> str:
    change = sp.simplify(delta)
    if change.is_number and change.is_real:
        if change < 0:
            mag = _speak_number(-change)
            return (
                f"{_speak_linear_side(lhs, variable)} minus {mag} equals "
                f"{_speak_linear_side(rhs, variable)} minus {mag}"
            )
        if change > 0:
            mag = _speak_number(change)
            return (
                f"{_speak_linear_side(lhs, variable)} plus {mag} equals "
                f"{_speak_linear_side(rhs, variable)} plus {mag}"
            )
    var = sp.symbols(variable)
    coef = sp.simplify(change.coeff(var, 1)) if change.free_symbols else 0
    if coef != 0 and sp.simplify(change - coef * var) == 0:
        if coef < 0:
            term = variable if coef == -1 else f"{_speak_number(-coef)} {variable}"
            return (
                f"{_speak_linear_side(lhs, variable)} minus {term} equals "
                f"{_speak_linear_side(rhs, variable)} minus {term}"
            )
        term = variable if coef == 1 else f"{_speak_number(coef)} {variable}"
        return (
            f"{_speak_linear_side(lhs, variable)} plus {term} equals "
            f"{_speak_linear_side(rhs, variable)} plus {term}"
        )
    return _speak_equation(lhs + delta, rhs + delta, variable)


def _balanced_divide_tex(lhs: sp.Expr, rhs: sp.Expr, divisor: sp.Expr) -> str:
    return (
        rf"\frac{{{sp.latex(lhs)}}}{{{sp.latex(divisor)}}}"
        rf" = \frac{{{sp.latex(rhs)}}}{{{sp.latex(divisor)}}}"
    )


def _linear_isolate_steps(
    lhs: sp.Expr, rhs: sp.Expr, variable: str
) -> list[dict[str, Any]]:
    """Pedagogical moves to isolate a linear unknown, with visible balance steps."""
    var = sp.symbols(variable)
    lhs, rhs = sp.expand(lhs), sp.expand(rhs)
    if sp.Poly(lhs, var).degree() > 1 or sp.Poly(rhs, var).degree() > 1:
        raise ValueError("expression is not linear in the variable")

    steps: list[dict[str, Any]] = []

    def append_additive_step(
        title: str, explanation: str, delta: sp.Expr
    ) -> None:
        nonlocal lhs, rhs
        new_lhs, new_rhs = sp.expand(lhs + delta), sp.expand(rhs + delta)
        spoken = _speak_prose(explanation)
        steps.append(
            {
                "title": title,
                "explanation": explanation,
                "speech": (
                    f"{spoken} {BEAT} "
                    f"So {_speak_balanced(lhs, rhs, delta, variable)}. {BEAT} "
                    f"That simplifies to {_speak_equation(new_lhs, new_rhs, variable)}."
                ),
                "math": [
                    _balanced_op_tex(lhs, rhs, delta),
                    _equation_tex(new_lhs, new_rhs),
                ],
            }
        )
        lhs, rhs = new_lhs, new_rhs

    def append_divide_step(title: str, explanation: str, divisor: sp.Expr) -> None:
        nonlocal lhs, rhs
        new_lhs, new_rhs = sp.simplify(lhs / divisor), sp.simplify(rhs / divisor)
        spoken = _speak_prose(explanation)
        divisor_words = _speak_number(divisor)
        steps.append(
            {
                "title": title,
                "explanation": explanation,
                "speech": (
                    f"{spoken} {BEAT} "
                    f"{_speak_linear_side(lhs, variable)} over {divisor_words} equals "
                    f"{_speak_linear_side(rhs, variable)} over {divisor_words}. {BEAT} "
                    f"That simplifies to {_speak_equation(new_lhs, new_rhs, variable)}."
                ),
                "math": [
                    _balanced_divide_tex(lhs, rhs, divisor),
                    _equation_tex(new_lhs, new_rhs),
                ],
            }
        )
        lhs, rhs = new_lhs, new_rhs

    rhs_var = rhs.coeff(var, 1)
    if rhs_var != 0:
        delta = -rhs_var * var
        mag = sp.simplify(abs(rhs_var))
        var_term = variable if mag == 1 else f"{sp.latex(mag)}{variable}"
        if rhs_var > 0:
            expl = f"Subtract ${var_term}$ from both sides."
        else:
            expl = f"Add ${var_term}$ to both sides."
        append_additive_step("Collect the variable", expl, delta)

    const_lhs = lhs.coeff(var, 0)
    if const_lhs != 0:
        delta = -const_lhs
        if const_lhs > 0:
            expl = f"Subtract ${sp.latex(const_lhs)}$ from both sides."
        else:
            expl = f"Add ${sp.latex(-const_lhs)}$ to both sides."
        append_additive_step("Isolate the variable term", expl, delta)

    coef = lhs.coeff(var, 1)
    if coef == 0:
        raise ValueError("variable does not appear in the equation")
    if coef != 1:
        expl = f"Divide both sides by ${sp.latex(coef)}$."
        append_divide_step("Solve for the variable", expl, coef)

    return steps


def _line_eq_tex(a: float, b: float, c: float) -> str:
    left = _term_tex(a, "x", leading=True) + _term_tex(b, "y")
    return f"{left or '0'} = {_fmt(c)}"


def _plane_eq_tex(a: float, b: float, c: float, d: float) -> str:
    left = (
        _term_tex(a, "x", leading=True)
        + _term_tex(b, "y")
        + _term_tex(c, "z")
    )
    return f"{left or '0'} = {_fmt(d)}"


def _sym_coef(value: float) -> sp.Expr:
    if abs(value - round(value)) < 1e-9:
        return sp.Integer(int(round(value)))
    return sp.Rational(sp.nsimplify(value))


def _quadratic_equation_tex(a: float, b: float, c: float) -> str:
    """School-style quadratic, e.g. x^2 - 5x + 6 = 0."""
    x = sp.symbols("x")
    poly = _sym_coef(a) * x**2 + _sym_coef(b) * x + _sym_coef(c)
    return sp.latex(poly) + " = 0"


def _quadratic_equation_plain(a: float, b: float, c: float) -> str:
    """Compact equation for plot_2d, e.g. x^2 - 5x + 6 = 0."""
    return _quadratic_equation_tex(a, b, c).replace("{", "").replace("}", "").replace(" ", "")


def _quadratic_factored_tex(a: float, b: float, c: float) -> str:
    x = sp.symbols("x")
    poly = _sym_coef(a) * x**2 + _sym_coef(b) * x + _sym_coef(c)
    roots = sorted(float(sp.N(r)) for r in sp.solve(poly, x) if r.is_real)
    if not roots:
        return sp.latex(sp.factor(poly, x))
    factors = []
    for root in roots:
        if abs(root - round(root)) < 1e-9:
            r = int(round(root))
            if r >= 0:
                factors.append(f"(x - {r})")
            else:
                factors.append(f"(x + {-r})")
        else:
            factors.append(f"\\left(x - {_fmt(root)}\\right)")
    body = "".join(factors)
    a_int = _sym_coef(a)
    if a_int == 1:
        return body
    if a_int == -1:
        return f"-{body}"
    return f"{sp.latex(a_int)}{body}"


def _quadratic_check_tex(a: float, b: float, c: float, root: float) -> str:
    r = _fmt(root)
    b_sign = "+" if b >= 0 else "-"
    c_sign = "+" if c >= 0 else "-"
    return rf"{r}^{{2}} {b_sign} {_fmt(abs(b))}({r}) {c_sign} {_fmt(abs(c))} = 0"


def _int_coef(value: float) -> int | None:
    if abs(value - round(value)) < 1e-9:
        return int(round(value))
    return None


def _find_factor_pair(sum_target: int, product_target: int) -> tuple[int, int] | None:
    """Integers p, q with p+q=sum_target and pq=product_target."""
    if product_target == 0:
        if sum_target == 0:
            return (0, 0)
        return None
    seen: set[tuple[int, int]] = set()
    limit = max(abs(product_target) * 2, 32)
    for p in range(-limit, limit + 1):
        if p == 0:
            continue
        if product_target % p != 0:
            continue
        q = product_target // p
        key = (min(p, q), max(p, q))
        if key in seen:
            continue
        seen.add(key)
        if p + q == sum_target:
            ordered = (p, q) if p > q else (q, p)
            return ordered
    return None


def _x_shift_tex(p: int) -> str:
    """Binomial x+p in factored form, e.g. p=-2 -> x-2."""
    if p >= 0:
        return f"x + {p}"
    return f"x - {abs(p)}"


def _split_quadratic_tex(a: int, p: int, q: int, c: int) -> str:
    """Expanded form with middle term split, e.g. x^2 - 2x - 3x + 6 = 0."""
    if a == 1:
        lead = "x^{2}"
    elif a == -1:
        lead = "-x^{2}"
    else:
        lead = f"{a}x^{{2}}"
    p_term = f"- {abs(p)}x" if p < 0 else (f"+ {p}x" if p != 1 else "+ x")
    q_term = f"- {abs(q)}x" if q < 0 else (f"+ {q}x" if q != 1 else "+ x")
    c_term = f"+ {c}" if c >= 0 else f"- {abs(c)}"
    return f"{lead} {p_term} {q_term} {c_term} = 0"


def _group_quadratic_tex(a: int, p: int, q: int, c: int) -> str:
    """Factor by grouping, e.g. x(x-2) - 3(x-2) = 0."""
    if a == 1 or a == -1:
        inner = _x_shift_tex(p)
        if a == 1:
            first = f"x({inner})"
        else:
            first = f"-x({inner})"
        if q == 1:
            second = f"+ ({inner})"
        elif q == -1:
            second = f"- ({inner})"
        elif q > 0:
            second = f"+ {q}({inner})"
        else:
            second = f"- {abs(q)}({inner})"
        return f"{first} {second} = 0"
    x = sp.symbols("x")
    part1 = sp.factor(_sym_coef(a) * x**2 + _sym_coef(p) * x)
    part2 = sp.factor(_sym_coef(q) * x + _sym_coef(c))
    return sp.latex(part1) + " + " + sp.latex(part2) + " = 0"


def _pair_summary_tex(p: int, q: int, product: int, total: int) -> str:
    return rf"({p}) \cdot ({q}) = {product},\quad ({p}) + ({q}) = {total}"


def _quadratic_factor_steps(a: float, b: float, c: float) -> list[dict[str, Any]]:
    """Deterministic factor-by-grouping steps when an integer pair exists."""
    ai, bi, ci = _int_coef(a), _int_coef(b), _int_coef(c)
    if ai is None or bi is None or ci is None or ai == 0:
        return []

    if ai == 1 or ai == -1:
        pair = _find_factor_pair(bi, ci)
        if pair is None:
            return []
        p, q = pair
        product_label = ci
        return [
            {
                "title": "Find two numbers",
                "explanation": (
                    f"Find two numbers that multiply to ${product_label}$ "
                    f"and add to ${_fmt(bi)}$."
                ),
                "speech": (
                    f"Find two numbers that multiply to {_speak_number(product_label)} "
                    f"and add to {_speak_number(bi)}. {BEAT} "
                    f"Those numbers are {_speak_number(p)} and {_speak_number(q)}."
                ),
                "math": [_pair_summary_tex(p, q, product_label, bi)],
            },
            {
                "title": "Split the middle term",
                "explanation": (
                    f"Rewrite the ${_fmt(bi)}x$ term using ${p}$ and ${q}$."
                ),
                "speech": (
                    f"Rewrite the middle term using {_speak_number(p)} and {_speak_number(q)}. "
                    f"{BEAT} Split it into those two terms."
                ),
                "math": [_split_quadratic_tex(ai, p, q, ci)],
            },
            {
                "title": "Factor by grouping",
                "explanation": "Group the four terms and pull out the common binomial.",
                "speech": (
                    f"Group the four terms and pull out the common binomial. {BEAT} "
                    f"First, group them. {BEAT} "
                    "That factors into a pair of binomials equal to zero."
                ),
                "math": [
                    _group_quadratic_tex(ai, p, q, ci),
                    f"{_quadratic_factored_tex(a, b, c)} = 0",
                ],
            },
        ]

    # ac method for a != 1
    pair = _find_factor_pair(bi, ai * ci)
    if pair is None:
        return []
    p, q = pair
    product_label = ai * ci
    return [
        {
            "title": "Find two numbers",
            "explanation": (
                f"Multiply $a \\cdot c = {_fmt(ai)} \\cdot {_fmt(ci)} = {_fmt(ai * ci)}$. "
                f"Find two numbers that multiply to ${_fmt(ai * ci)}$ "
                f"and add to ${_fmt(bi)}$."
            ),
            "speech": (
                f"Multiply a times c to get {_speak_number(product_label)}. {BEAT} "
                f"Find two numbers that multiply to {_speak_number(product_label)} "
                f"and add to {_speak_number(bi)}. {BEAT} "
                f"Those numbers are {_speak_number(p)} and {_speak_number(q)}."
            ),
            "math": [_pair_summary_tex(p, q, ai * ci, bi)],
        },
        {
            "title": "Split the middle term",
            "explanation": f"Rewrite the ${_fmt(bi)}x$ term using ${p}$ and ${q}$.",
            "speech": (
                f"Rewrite the middle term using {_speak_number(p)} and {_speak_number(q)}. "
                f"{BEAT} Split it into those two terms."
            ),
            "math": [_split_quadratic_tex(ai, p, q, ci)],
        },
        {
            "title": "Factor by grouping",
            "explanation": "Group and pull out the common binomial.",
            "speech": (
                f"Group the four terms and pull out the common binomial. {BEAT} "
                f"First, group them. {BEAT} "
                "That factors into a pair of binomials equal to zero."
            ),
            "math": [
                _group_quadratic_tex(ai, p, q, ci),
                f"{_quadratic_factored_tex(a, b, c)} = 0",
            ],
        },
    ]


def _factor_zero_lines(roots: list[float]) -> list[str]:
    lines: list[str] = []
    for root in roots:
        r = int(round(root)) if abs(root - round(root)) < 1e-9 else None
        if r is not None:
            lines.append(f"{_x_shift_tex(-r)} = 0")
        else:
            lines.append(f"x - {_fmt(root)} = 0")
    return lines


def _plan(raw: dict[str, Any]) -> dict[str, Any]:
    raw["version"] = PLAN_VERSION
    for step in raw.get("steps") or []:
        if isinstance(step, dict) and not str(step.get("speech") or "").strip():
            step["speech"] = _auto_step_speech(step)
    return validate_plan(raw)


class CatalogFreeform(Exception):
    """Catalog planners cannot teach this problem; use the freeform LLM teacher."""


def _problem(tool_input: dict[str, Any], *, name: str) -> str:
    problem = str(tool_input.get("problem_statement") or "").strip()
    if not problem:
        raise ValueError(f"{name} requires problem_statement")
    return problem



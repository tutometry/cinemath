"""Speakable prose for math (sympy-backed)."""

from __future__ import annotations

import re

import sympy as sp

_IMPLICIT_MUL = re.compile(r"(\d)([a-zA-Z])")
_COEF_VAR = re.compile(r"([a-zA-Z])([xyz])(?=(\*\*|\b|\+|\-|=|$))")
_BRACE_CONTENT = re.compile(r"\{([^{}]+)\}")
_POWER = re.compile(r"\^(\{)?([^}^]+)(\})?")
_INTEGRAL = re.compile(
    r"\\int(?:_\{([^}]*)\})?(?:\^\{([^}]*)\})?\s*(.+?)\\,?\s*d([a-zA-Z])\b",
)
_PARTIAL_DERIV = re.compile(
    r"\\frac\{\\partial\s*([^}]*)\}\{\\partial\s*([^}]*)\}\s*=\s*(.+)",
    re.DOTALL,
)
_PRIME_DERIV = re.compile(r"^f'\(([^)]*)\)\s*=\s*(.+)$", re.DOTALL)


def speak_number(value: sp.Expr | float | int) -> str:
    if not isinstance(value, sp.Expr):
        value = sp.nsimplify(value)
    value = sp.simplify(value)
    if value.is_Integer:
        return _cardinal(int(value))
    if value.is_Rational and value.q != 1:
        return f"{_cardinal(int(value.p))} over {_cardinal(int(value.q))}"
    if value.is_Rational and value.q == 1:
        return _cardinal(int(value.p))
    return str(value)


def latex_fragment_to_speech(fragment: str) -> str:
    """Turn an inline-math LaTeX fragment into TTS-friendly words."""
    return speak_latex_math(fragment)


def speak_latex_math(tex: str) -> str:
    """Speak a board-style LaTeX line (integrals, derivatives, equations)."""
    frag = tex.strip()
    if not frag:
        return ""
    while frag.startswith("="):
        frag = frag[1:].strip()
    partial = _PARTIAL_DERIV.match(frag)
    if partial:
        func, var, rhs = partial.group(1).strip(), partial.group(2).strip(), partial.group(3)
        return (
            f"the partial derivative of {func} with respect to {var} equals "
            f"{speak_latex_math(rhs)}"
        )
    prime = _PRIME_DERIV.match(frag)
    if prime:
        var, rhs = prime.group(1).strip(), prime.group(2).strip()
        return f"f prime of {var} equals {speak_latex_math(rhs)}"
    int_m = _INTEGRAL.search(frag)
    if int_m and frag.count("\\int") == 1 and "=" not in frag:
        lo, hi, body, var = int_m.group(1), int_m.group(2), int_m.group(3), int_m.group(4)
        return _speak_integral_phrase(body, var, lo, hi)
    if "=" in frag:
        lhs, rhs = frag.split("=", 1)
        return f"{speak_latex_math(lhs)} equals {speak_latex_math(rhs)}"
    parsed = _try_parse(frag)
    if parsed is not None:
        return speak_expr(parsed)
    return _heuristic_latex_words(frag)


def _speak_integral_phrase(
    body: str,
    variable: str,
    lower: str | None,
    upper: str | None,
) -> str:
    integrand = speak_latex_math(body.strip())
    if lower is not None and upper is not None:
        lo = speak_latex_math(lower)
        hi = speak_latex_math(upper)
        return f"the integral from {lo} to {hi} of {integrand} d {variable}"
    return f"the integral of {integrand} d {variable}"


def _speak_integral_expr(expr: sp.Integral) -> str:
    integrand = speak_expr(expr.function)
    limits = expr.limits
    if not limits:
        return f"the integral of {integrand}"
    var, *bounds = limits[0]
    var_name = speak_expr(var)
    if len(bounds) == 2:
        lo, hi = speak_expr(bounds[0]), speak_expr(bounds[1])
        return f"the integral from {lo} to {hi} of {integrand} d {var_name}"
    return f"the integral of {integrand} d {var_name}"


def speak_expr(expr: sp.Expr) -> str:
    if isinstance(expr, sp.Integral):
        return _speak_integral_expr(expr)
    if isinstance(expr, sp.Derivative):
        inner = expr.expr
        vars_ = expr.variables
        if len(vars_) == 1:
            v = vars_[0]
            return (
                f"the derivative of {speak_expr(inner)} with respect to {speak_expr(v)}"
            )
    if isinstance(expr, sp.Equality):
        return f"{speak_expr(expr.lhs)} equals {speak_expr(expr.rhs)}"
    expr = sp.expand(expr)
    var = _main_symbol(expr)
    if var is not None and expr.has(var):
        return _speak_univariate(expr, var)
    if expr.is_Number or (expr.is_Integer or expr.is_Rational):
        return speak_number(expr)
    if expr.is_Symbol:
        return str(expr)
    return _heuristic_latex_words(sp.srepr(expr))


def _try_parse(frag: str) -> sp.Expr | None:
    normalized = _normalize_for_sympify(frag)
    if not normalized:
        return None
    if "=" in normalized:
        lhs_s, rhs_s = normalized.split("=", 1)
        try:
            return sp.Eq(sp.sympify(lhs_s), sp.sympify(rhs_s))
        except (sp.SympifyError, TypeError, ValueError):
            return None
    try:
        return sp.sympify(normalized)
    except (sp.SympifyError, TypeError, ValueError):
        return None


def _normalize_for_sympify(frag: str) -> str:
    s = frag.strip()
    int_m = _INTEGRAL.search(s)
    if int_m and s.count("\\int") == 1:
        lo, hi, body, var = int_m.group(1), int_m.group(2), int_m.group(3), int_m.group(4)
        inner = _normalize_for_sympify(body)
        var_sym = sp.symbols(var)
        integrand = sp.sympify(inner)
        if lo is not None and hi is not None:
            lo_e = sp.sympify(_normalize_for_sympify(lo))
            hi_e = sp.sympify(_normalize_for_sympify(hi))
            return str(sp.Integral(integrand, (var_sym, lo_e, hi_e)))
        return str(sp.Integral(integrand, var_sym))
    s = s.replace(r"\,", " ").replace(r"\;", " ").replace(r"\quad", " ")
    s = s.replace(r"\cdot", "*").replace(r"\times", "*")
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\left|\\right", "", s)
    while _BRACE_CONTENT.search(s):
        s = _BRACE_CONTENT.sub(r"\1", s)
    s = _POWER.sub(lambda m: f"**{m.group(2).strip()}", s)
    s = _IMPLICIT_MUL.sub(r"\1*\2", s)
    s = _COEF_VAR.sub(r"\1*\2", s)
    s = re.sub(r"\s+", "", s)
    return s


def _main_symbol(expr: sp.Expr) -> sp.Symbol | None:
    syms = expr.free_symbols
    if not syms:
        return None
    if len(syms) == 1:
        return next(iter(syms))
    for name in ("x", "y", "t", "n", "a", "b", "c"):
        sym = sp.symbols(name)
        if sym in syms:
            return sym
    return next(iter(syms))


def _speak_univariate(expr: sp.Expr, var: sp.Symbol) -> str:
    if not expr.is_polynomial(var):
        return _heuristic_latex_words(sp.latex(expr))
    poly = sp.Poly(expr, var)
    degree = poly.degree()
    coeffs = poly.all_coeffs()
    chunks: list[str] = []
    first = True
    for index, coef in enumerate(coeffs):
        coef = sp.simplify(coef)
        if coef == 0:
            continue
        power = degree - index
        negative, magnitude = _split_sign(coef)
        body = _speak_monomial(magnitude, var, power)
        if first:
            chunks.append(f"negative {body}" if negative else body)
            first = False
        elif negative:
            chunks.append(f"minus {body}")
        else:
            chunks.append(f"plus {body}")
    return " ".join(chunks) if chunks else speak_number(0)


def _split_sign(coef: sp.Expr) -> tuple[bool, sp.Expr]:
    c = sp.simplify(coef)
    if c.is_number and c.is_real:
        return float(c) < 0, sp.Abs(c)
    if c.could_extract_minus_sign():
        return True, sp.simplify(-c)
    return False, c


def _speak_monomial(coef: sp.Expr, var: sp.Symbol, power: int) -> str:
    coef = sp.simplify(coef)
    if power == 0:
        if coef.is_Symbol:
            return str(coef)
        return speak_number(coef)
    var_part = _speak_var_power(var, power)
    if coef == 1:
        return var_part
    if coef.is_Symbol:
        return f"{coef} {var_part}"
    return f"{speak_number(coef)} {var_part}"


def _speak_var_power(var: sp.Symbol, power: int) -> str:
    name = str(var)
    if power == 1:
        return name
    if power == 2:
        return f"{name} squared"
    if power == 3:
        return f"{name} cubed"
    return f"{name} to the {speak_number(power)}"


def _heuristic_latex_words(frag: str) -> str:
    """Last resort when sympy cannot parse the fragment."""
    out = frag.strip()
    out = out.replace(r"\,", " ").replace(r"\;", " ").replace(r"\quad", " ")
    out = out.replace(r"\cdot", " times ").replace(r"\times", " times ")
    out = re.sub(r"\\[a-zA-Z]+", " ", out)
    out = out.replace("{", "").replace("}", "")
    out = re.sub(r"\^2\b", " squared", out)
    out = re.sub(r"\^3\b", " cubed", out)
    out = out.replace("^", " to the ").replace("_", " ")
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _cardinal(number: int) -> str:
    if number < 0:
        return f"negative {_cardinal(-number)}"
    names = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
        11: "eleven",
        12: "twelve",
        13: "thirteen",
        14: "fourteen",
        15: "fifteen",
        16: "sixteen",
        17: "seventeen",
        18: "eighteen",
        19: "nineteen",
        20: "twenty",
    }
    if number <= 20:
        return names[number]
    if number < 100:
        tens = [
            "",
            "",
            "twenty",
            "thirty",
            "forty",
            "fifty",
            "sixty",
            "seventy",
            "eighty",
            "ninety",
        ]
        ten, unit = divmod(number, 10)
        if unit == 0:
            return tens[ten]
        return f"{tens[ten]} {names[unit]}"
    return str(number)

"""Rule-system-neutral exact scalar arithmetic; no game rounding policy."""
import ast
from decimal import Decimal
from fractions import Fraction
import math


def exact(value):
    """Read configured decimal values by their written value, not binary noise."""
    if isinstance(value, bool):
        raise ValueError('boolean is not a numeric game quantity')
    if isinstance(value, Fraction):
        return value
    if isinstance(value, (int, Decimal)):
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('finite numeric quantity required')
        return Fraction(str(value))
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError('exact numeric literal required') from exc
    raise ValueError('integer, decimal, or rational quantity required')


def round_down(value):
    value = exact(value)
    return value.numerator // value.denominator


def round_up(value):
    value = exact(value)
    return -((-value.numerator) // value.denominator)


def multiply(*values):
    answer = Fraction(1)
    for value in values:
        answer *= exact(value)
    return answer


def evaluate(expression, variables):
    """Exact counterpart of the existing arithmetic-only formula language.

    Keep rational intermediates; the consuming rule selects rounding boundaries.
    Explicit floor/ceil within a formula are preserved as separate boundaries.
    """
    if not isinstance(expression, str):
        return exact(expression)
    parsed = ast.parse(expression.strip(), mode='eval')
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return exact(ast.get_source_segment(expression.strip(), node))
        if isinstance(node, ast.Name) and node.id in variables:
            return exact(variables[node.id])
        if isinstance(node, ast.UnaryOp):
            operand = visit(node.operand)
            if isinstance(node.op, ast.USub): return -operand
            if isinstance(node.op, ast.UAdd): return operand
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            if isinstance(node.op, ast.FloorDiv): return Fraction(round_down(left / right))
            if isinstance(node.op, ast.Pow) and right.denominator == 1: return left ** int(right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            functions = {'floor': round_down, 'ceil': round_up, 'min': min, 'max': max}
            if node.func.id in functions:
                return exact(functions[node.func.id](*(visit(arg) for arg in node.args)))
        raise ValueError('unsupported arithmetic formula token')
    value = visit(parsed.body)
    return value.numerator if value.denominator == 1 else value

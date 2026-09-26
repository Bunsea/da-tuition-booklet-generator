import os
import io
import re
import ast
import uuid
import tempfile
import operator as _op
from typing import Optional, Dict, Any

# Ensure matplotlib uses a safe persistent writable cache directory and non-interactive backend
_WORKSPACE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "matplotlib")
os.makedirs(_WORKSPACE_CACHE, exist_ok=True)
os.environ["MPLCONFIGDIR"] = _WORKSPACE_CACHE
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# DA Tuition Brand Color
DA_NAVY = "#1A3A8A"

class UnsafeExpressionError(ValueError):
    pass

_ALLOWED_BINOPS = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.Pow: _op.pow,
    ast.Mod: _op.mod,
    ast.FloorDiv: _op.floordiv,
}
_ALLOWED_UNARYOPS = {ast.UAdd: _op.pos, ast.USub: _op.neg}
_ALLOWED_FUNCS = {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "exp": np.exp, "log": np.log, "log10": np.log10, "log2": np.log2,
    "sqrt": np.sqrt, "abs": np.abs, "floor": np.floor, "ceil": np.ceil,
}

def _safe_eval_node(node, names):
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body, names)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](
            _safe_eval_node(node.left, names), _safe_eval_node(node.right, names)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_safe_eval_node(node.operand, names))
    if isinstance(node, ast.Call):
        if node.keywords or not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            fname = getattr(node.func, "id", "?")
            raise UnsafeExpressionError(f"Function '{fname}' is not allowed.")
        args = [_safe_eval_node(a, names) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        raise UnsafeExpressionError(f"Unknown variable '{node.id}'.")
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    raise UnsafeExpressionError(f"Disallowed expression element: {type(node).__name__}")

def safe_eval_math(expr_str: str, names: dict):
    """Evaluate a simple math expression string against an AST whitelist."""
    tree = ast.parse(expr_str, mode="eval")
    return _safe_eval_node(tree, names)

def parse_graph_spec(block: str) -> Optional[Dict[str, Any]]:
    data = {}
    for line in block.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Find separator: colon or equals sign
        sep = ":" if ":" in line else ("=" if "=" in line else None)
        if not sep:
            continue
        key, _, val = line.partition(sep)
        k = key.strip().lower()
        v = val.strip()

        if k in ["expr", "expression", "f(x)", "y", "fn", "function", "eqn", "equation"]:
            data["expr"] = v
        elif k in ["domain", "xrange", "x_range"]:
            parts = v.replace("[", "").replace("]", "").replace(",", ":").split(":")
            if len(parts) >= 2:
                data["xmin"] = parts[0].strip()
                data["xmax"] = parts[1].strip()
        elif k in ["range", "yrange", "y_range"]:
            parts = v.replace("[", "").replace("]", "").replace(",", ":").split(":")
            if len(parts) >= 2:
                data["ymin"] = parts[0].strip()
                data["ymax"] = parts[1].strip()
        else:
            data[k] = v

    def _f(k, default):
        try:
            return float(data[k])
        except Exception:
            return default

    g_type = data.get("type", "function")
    spec = {
        "type": g_type,
        "xmin": _f("xmin", -5.0),
        "xmax": _f("xmax", 5.0),
        "ymin": data.get("ymin"),
        "ymax": data.get("ymax"),
        "xlabel": data.get("xlabel", "x"),
        "ylabel": data.get("ylabel", "y"),
    }

    if g_type in ["function", "slope_field"]:
        if "expr" not in data:
            return None
        spec["expr"] = data["expr"]
    elif g_type == "normal":
        spec["mean"] = _f("mean", 0.0)
        spec["std"] = _f("std", 1.0)
        spec["shade_min"] = data.get("shade_min")
        spec["shade_max"] = data.get("shade_max")

    return spec

def draw_function_graph(spec: dict) -> Optional[bytes]:
    if not spec:
        return None
    g_type = spec.get("type", "function")
    fig, ax = plt.subplots(figsize=(6, 4))

    xmin, xmax = float(spec["xmin"]), float(spec["xmax"])
    auto_ymin, auto_ymax = (-5.0, 5.0)

    try:
        if g_type == "function":
            raw = spec["expr"].strip()
            raw = re.sub(r"^[yYfF]\s*[\(x\)]?\s*=\s*", "", raw)
            py_expr = raw.replace("^", "**")
            py_expr = re.sub(r"(\d)\s*\(", r"\1*(", py_expr)
            py_expr = re.sub(r"(\d)([a-df-wyzA-DF-WYZ])", r"\1*\2", py_expr)

            x = np.linspace(xmin, xmax, 1000)
            with np.errstate(divide="ignore", invalid="ignore"):
                y = safe_eval_math(py_expr, {"x": x, "pi": np.pi, "e": np.e})
            y = np.asarray(y, dtype=float)

            clip_val = max(abs(xmax - xmin) * 20, 200)
            with np.errstate(invalid="ignore"):
                y = np.where(np.abs(y) > clip_val, np.nan, y)
            ax.plot(x, y, color=DA_NAVY, linewidth=2)

            y_valid = y[np.isfinite(y)]
            if len(y_valid) > 0:
                pad = max((y_valid.max() - y_valid.min()) * 0.1, 0.5)
                auto_ymin, auto_ymax = y_valid.min() - pad, y_valid.max() + pad

        elif g_type == "slope_field":
            ymin = float(spec["ymin"]) if spec.get("ymin") else -5.0
            ymax = float(spec["ymax"]) if spec.get("ymax") else 5.0
            auto_ymin, auto_ymax = ymin, ymax

            raw = spec["expr"].strip()
            py_expr = raw.replace("^", "**")

            x_vals = np.linspace(xmin, xmax, 20)
            y_vals = np.linspace(ymin, ymax, 20)
            X, Y = np.meshgrid(x_vals, y_vals)

            with np.errstate(divide="ignore", invalid="ignore"):
                dy = safe_eval_math(py_expr, {"x": X, "y": Y, "pi": np.pi, "e": np.e})

            dx = np.ones_like(dy)
            norm = np.sqrt(dx**2 + dy**2)
            norm[norm == 0] = 1.0
            dx = dx / norm
            dy = dy / norm

            ax.quiver(X, Y, dx, dy, color=DA_NAVY, headwidth=1, headlength=0, pivot="middle", scale=30)

        elif g_type == "normal":
            mean = float(spec.get("mean", 0.0))
            std = float(spec.get("std", 1.0))
            x = np.linspace(mean - 4 * std, mean + 4 * std, 1000)
            y = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std) ** 2)
            ax.plot(x, y, color=DA_NAVY, linewidth=2)

            if spec.get("shade_min") and spec.get("shade_max"):
                s_min = float(spec["shade_min"])
                s_max = float(spec["shade_max"])
                sx = np.linspace(s_min, s_max, 100)
                sy = (1 / (std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((sx - mean) / std) ** 2)
                ax.fill_between(sx, sy, alpha=0.3, color=DA_NAVY)

            xmin, xmax = mean - 4 * std, mean + 4 * std
            auto_ymin, auto_ymax = 0, y.max() * 1.2
            ax.set_xticks(
                [mean - 3 * std, mean - 2 * std, mean - std, mean, mean + std, mean + 2 * std, mean + 3 * std]
            )

        ymin = float(spec["ymin"]) if spec.get("ymin") else auto_ymin
        ymax = float(spec["ymax"]) if spec.get("ymax") else auto_ymax

        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.spines["left"].set_position("zero")
        ax.spines["bottom"].set_position("zero")
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.set_xlabel(spec.get("xlabel", "x"), loc="right")
        ax.set_ylabel(spec.get("ylabel", "y"), loc="top")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        plt.close(fig)
        return None

def inject_python_graphs(text: str, work_dir: str) -> str:
    """
    Renders any GRAPH_START...GRAPH_END or ```graph ... ``` blocks into PNGs inside work_dir and
    swaps them for \\includegraphics.
    """
    if not text:
        return text

    pattern = r"(?:GRAPH_START|```graph)([\s\S]*?)(?:GRAPH_END|```)"
    
    def replacer(match):
        block = match.group(1).strip()
        gspec = parse_graph_spec(block)
        if gspec:
            png_bytes = draw_function_graph(gspec)
            if png_bytes:
                img_name = f"graph_{uuid.uuid4().hex[:10]}.png"
                img_path = os.path.join(work_dir, img_name)
                with open(img_path, "wb") as f:
                    f.write(png_bytes)
                img_url_path = img_path.replace("\\", "/")
                return f"\n\\begin{{center}}\\includegraphics[width=0.55\\textwidth]{{{img_url_path}}}\\end{{center}}\n"
        return "\n\\textit{[Graph Generation Failed]}\n"

    return re.sub(pattern, replacer, text)

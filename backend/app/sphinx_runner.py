"""
sphinx_runner.py — Runs Sphinx CLI on a generated notebook and streams output.
Called by the /sphinx/stream route in app.py.
"""

import json, os, uuid, subprocess, tempfile, textwrap, logging, shutil, socket, time
from pathlib import Path

log = logging.getLogger(__name__)

SPHINX_API_KEY = os.getenv("SPHINX_API_KEY", "")
NODE_BIN  = "/root/.nvm/versions/node/v18.20.8/bin/node"
SPHINX_CJS = "/usr/local/lib/python3.10/dist-packages/sphinx_cli/sphinx-cli.cjs"

OUTPUT_SCHEMA = {
    "risk_summary": {
        "type": "string",
        "description": "One sentence summary of the overall contamination risk level"
    },
    "critical_cells": {
        "type": "string",
        "description": "Comma-separated row,col coordinates of critical risk cells e.g. (0,2),(1,3)"
    },
    "cleaning_sequence": {
        "type": "string",
        "description": "Step-by-step recommended cleaning sequence referencing specific cells"
    },
    "protocol": {
        "type": "string",
        "description": "Recommended protocol: UV-C + double wipe, Microfiber spray, or Standard wipe-down"
    },
    "confidence": {
        "type": "string",
        "description": "Confidence level and any caveats about the analysis"
    }
}


def free_port() -> int:
    s = socket.socket(); s.bind(('', 0)); p = s.getsockname()[1]; s.close(); return p


def session_to_notebook(session: dict, analysis: dict) -> str:
    h = session["grid_h"]
    w = session["grid_w"]

    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11.0"}
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": textwrap.dedent(f"""
                    # CleanSight — Surface Contamination Session Analysis
                    **Session:** {session['session_id']}
                    **Surface:** {session['surface_type']} (`{session['surface_id']}`)
                    **Room:** {session['room_id']}
                    **Duration:** {analysis['durStr']}
                    **Grid:** {h}×{w} ({analysis['totalCells']} cells)
                    **Coverage:** {analysis['covPct']}% | **High-touch uncleaned:** {analysis['htUncleaned']}/{analysis['htTotal']}
                    **Risk counts:** {json.dumps(analysis['counts'])}
                """).strip()
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": textwrap.dedent(f"""
                    import json, numpy as np, pandas as pd

                    session = {json.dumps(session, indent=2)}

                    coverage   = np.array(session['coverage_count_grid'])
                    high_touch = np.array(session['high_touch_mask'])

                    risk_grid = []
                    for r in range({h}):
                        row = []
                        for c in range({w}):
                            cov = coverage[r, c]
                            ht  = high_touch[r, c] == 1
                            if ht and cov == 0:        row.append("CRITICAL")
                            elif ht and cov == 1:      row.append("HIGH")
                            elif not ht and cov == 0:  row.append("MEDIUM")
                            elif ht and cov >= 2:      row.append("LOW")
                            else:                      row.append("CLEAR")
                        risk_grid.append(row)

                    cols = [f'Col{{c}}' for c in range({w})]
                    idx  = [f'Row{{r}}' for r in range({h})]

                    print("=== Coverage grid (wipe count per cell) ===")
                    print(pd.DataFrame(coverage, columns=cols, index=idx).to_string())
                    print()
                    print("=== High-touch mask (1 = critical zone) ===")
                    print(pd.DataFrame(high_touch, columns=cols, index=idx).to_string())
                    print()
                    print("=== Risk classification per cell ===")
                    print(pd.DataFrame(risk_grid, columns=cols, index=idx).to_string())
                    print()
                    print(f"Coverage: {analysis['covPct']}% | Critical: {analysis['counts']['critical']} | High: {analysis['counts']['high']}")
                    print(f"Focus cells: {[(c['r'], c['c']) for c in analysis['focus']]}")
                """).strip()
            }
        ]
    }
    return json.dumps(notebook, indent=2)


def build_prompt(session: dict, analysis: dict) -> str:
    focus = ", ".join(f"row {c['r']} col {c['c']}" for c in analysis["focus"]) or "none"
    return (
        f"You are a hospital infection control expert. "
        f"Analyze this {session['surface_type']} surface cleaning session in room {session['room_id']}. "
        f"The coverage grid shows wipe counts per cell. The high-touch mask marks infection-critical zones. "
        f"Coverage is {analysis['covPct']}% overall with {analysis['counts']['critical']} CRITICAL cells "
        f"(high-touch + zero coverage) and {analysis['counts']['high']} HIGH risk cells. "
        f"Focus cells needing immediate attention: {focus}. "
        f"Reason step by step: (1) what the spatial pattern reveals about cleaning behaviour, "
        f"(2) which cells are highest priority and why with exact row/col coordinates, "
        f"(3) optimal cleaning sequence, "
        f"(4) recommended protocol. Be precise and clinical."
    )


def run_sphinx_stream(session: dict, analysis: dict):
    tmpdir = tempfile.mkdtemp(prefix="cleansight_")
    nb_path      = Path(tmpdir) / f"{session['session_id']}.ipynb"
    schema_path  = Path(tmpdir) / "schema.json"
    session_path = Path(tmpdir) / "session.json"
    jp_proc      = None

    try:
        nb_path.write_text(session_to_notebook(session, analysis))
        schema_path.write_text(json.dumps(OUTPUT_SCHEMA, indent=2))
        session_path.write_text(json.dumps(session, indent=2))

        prompt = build_prompt(session, analysis)

        env = os.environ.copy()
        if SPHINX_API_KEY:
            env["SPHINX_API_KEY"] = SPHINX_API_KEY

        yield "data: " + json.dumps({"token": f"🧠 Sphinx AI analyzing {session['session_id']}…\n\n"}) + "\n\n"

        # ── Start a temporary Jupyter server ─────────────────────────────────
        jp_port  = free_port()
        jp_token = uuid.uuid4().hex
        jp_proc  = subprocess.Popen(
            [
                "jupyter", "server",
                "--no-browser",
                f"--port={jp_port}",
                f"--ServerApp.token={jp_token}",
                "--ServerApp.password=",
                "--ServerApp.disable_check_xsrf=True",
                f"--notebook-dir={tmpdir}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=tmpdir,
        )

        yield "data: " + json.dumps({"token": "⏳ Starting Jupyter server…\n"}) + "\n\n"
        time.sleep(5)  # wait for Jupyter to be ready

        jp_url = f"http://localhost:{jp_port}?token={jp_token}"

        # ── Run Sphinx via node directly ──────────────────────────────────────
        cmd = [
            NODE_BIN,
            SPHINX_CJS,
            "chat",
            "--jupyter-server-url", jp_url,
            "--notebook-filepath", str(nb_path),
            "--prompt", prompt,
            "--output-schema", str(schema_path),
            "--no-web-search",
            "--no-memory-write",
            "--no-memory-read",
            "--verbose",
        ]

        yield "data: " + json.dumps({"token": "✓ Jupyter ready · launching Sphinx…\n"}) + "\n\n"

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=tmpdir,
        )

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue

            if line.startswith("Sphinx: "):
                reasoning = line[len("Sphinx: "):]
                yield "data: " + json.dumps({"token": reasoning + "\n\n"}) + "\n\n"
                continue

            if "[INFO]" in line:
                if "initialized successfully" in line:
                    yield "data: " + json.dumps({"token": "✓ Sphinx AI initialized\n"}) + "\n\n"
                elif "performing an action of type: assistantAddCell" in line:
                    yield "data: " + json.dumps({"token": "⚡ Running analysis code…\n"}) + "\n\n"
                continue

            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    structured = json.loads(stripped)
                    yield "data: " + json.dumps({"structured": structured}) + "\n\n"
                    continue
                except json.JSONDecodeError:
                    pass

            if "[ERROR]" in line:
                yield "data: " + json.dumps({"token": f"⚠ {line}\n"}) + "\n\n"

        proc.wait()

        if proc.returncode == 0:
            try:
                nb = json.loads(nb_path.read_text())
                for cell in nb.get("cells", []):
                    if cell["cell_type"] == "markdown":
                        src = "".join(cell.get("source", []))
                        if src and "CleanSight" not in src:
                            yield "data: " + json.dumps({"token": src + "\n\n"}) + "\n\n"
                    elif cell["cell_type"] == "code":
                        for output in cell.get("outputs", []):
                            text = ""
                            if output.get("output_type") in ("stream", "execute_result"):
                                text = "".join(output.get("text", []))
                            elif output.get("output_type") == "display_data":
                                text = "".join(output.get("data", {}).get("text/plain", []))
                            if text.strip():
                                yield "data: " + json.dumps({"token": text + "\n"}) + "\n\n"
            except Exception as e:
                log.warning(f"Could not parse output notebook: {e}")

            yield "data: " + json.dumps({"token": "\n✅ Analysis complete.\n"}) + "\n\n"
        else:
            yield "data: " + json.dumps({"error": f"Sphinx exited with code {proc.returncode}"}) + "\n\n"

    except Exception as e:
        log.error(f"Sphinx runner error: {e}")
        yield "data: " + json.dumps({"error": str(e)}) + "\n\n"
    finally:
        if jp_proc:
            jp_proc.terminate()
        shutil.rmtree(tmpdir, ignore_errors=True)
        yield "data: [DONE]\n\n"
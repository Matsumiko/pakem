#!/usr/bin/env python3
"""Jalankan evals Pakem: satu sesi agent per prompt, lalu nilai assertion-nya.

Runner ini tidak tahu apa-apa soal model. Ia menyiapkan direktori bersih, memberi
prompt ke perintah agent lewat stdin, merekam transkrip, lalu menyerahkan penilaian
ke perintah judge. Tanpa judge, transkrip tetap direkam tapi assertion tidak dinilai.

Contoh:

    python3 scripts/run_evals.py --list
    python3 scripts/run_evals.py --validate

    python3 scripts/run_evals.py --agent-cmd "hermes run --skill ." \\
        --judge-cmd "python3 judge.py" --out evals-results.json

Kontrak agent-cmd: membaca prompt dari stdin, bekerja di cwd (direktori sandbox),
boleh menulis apa pun. exit code dicatat, bukan dinilai.

Kontrak judge-cmd: menerima satu objek JSON di stdin (lihat build_judge_payload),
menulis satu objek JSON di stdout:

    {"results": [{"assertion": "...", "pass": true, "why": "..."}]}

Setiap assertion pada eval harus muncul tepat sekali. Yang tidak dinilai dihitung gagal.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS_FILE = HERE.parent / "evals" / "evals.json"
MAX_TRANSCRIPT = 20_000
MAX_LISTED_FILES = 200


def load_evals(path: Path = EVALS_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(doc: dict) -> list[str]:
    """Cek struktural. Mengembalikan daftar masalah; kosong berarti sehat."""
    problems = []
    if not isinstance(doc, dict):
        return ["evals.json harus berupa object"]
    evals = doc.get("evals")
    if not isinstance(evals, list) or not evals:
        return ["evals harus berupa array yang tidak kosong"]
    seen = set()
    for index, item in enumerate(evals):
        label = f"eval[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{label}: bukan object")
            continue
        for key in ("id", "prompt", "expected_output", "assertions"):
            if key not in item:
                problems.append(f"{label}: '{key}' tidak ada")
        eval_id = item.get("id")
        if eval_id in seen:
            problems.append(f"{label}: id duplikat {eval_id!r}")
        seen.add(eval_id)
        if not str(item.get("prompt", "")).strip():
            problems.append(f"{label}: prompt kosong")
        assertions = item.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            problems.append(f"{label}: assertions harus array tidak kosong")
        elif any(not str(a).strip() for a in assertions):
            problems.append(f"{label}: ada assertion kosong")
    return problems


def snapshot(directory: Path) -> list[dict]:
    """Daftar file di sandbox, supaya judge bisa melihat hasil kerja agent."""
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and len(files) < MAX_LISTED_FILES:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            files.append({"path": path.relative_to(directory).as_posix(), "bytes": size})
    return files


def run_agent(command: str, prompt: str, cwd: Path, timeout: int) -> dict:
    started = time.time()
    try:
        result = subprocess.run(shlex.split(command), input=prompt, cwd=cwd, text=True,
                                capture_output=True, timeout=timeout, check=False)
        return {"exit_code": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "seconds": round(time.time() - started, 1),
                "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": None,
                "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else "",
                "seconds": round(time.time() - started, 1),
                "timed_out": True}
    except OSError as exc:
        return {"exit_code": None, "stdout": "", "stderr": f"agent tidak bisa dijalankan: {exc}",
                "seconds": 0.0, "timed_out": False}


def build_judge_payload(item: dict, run: dict, files: list[dict]) -> dict:
    transcript = (run["stdout"] + "\n" + run["stderr"]).strip()
    return {
        "eval_id": item.get("id"),
        "prompt": item.get("prompt"),
        "expected_output": item.get("expected_output"),
        "assertions": item.get("assertions", []),
        "exit_code": run["exit_code"],
        "timed_out": run["timed_out"],
        "transcript": transcript[:MAX_TRANSCRIPT],
        "transcript_truncated": len(transcript) > MAX_TRANSCRIPT,
        "files": files,
    }


def judge(command: str, payload: dict, timeout: int) -> tuple[list[dict], str]:
    """Kembalikan (results, error). error kosong berarti judge berhasil."""
    try:
        result = subprocess.run(shlex.split(command), input=json.dumps(payload), text=True,
                                capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return [], "judge timeout"
    except OSError as exc:
        return [], f"judge tidak bisa dijalankan: {exc}"
    if result.returncode != 0:
        return [], f"judge exit {result.returncode}: {(result.stderr or '').strip()[:300]}"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], "output judge bukan JSON"
    results = data.get("results")
    if not isinstance(results, list):
        return [], "judge harus mengembalikan {\"results\": [...]}"
    clean = []
    for entry in results:
        if not isinstance(entry, dict) or "assertion" not in entry:
            continue
        clean.append({"assertion": str(entry["assertion"]),
                      "pass": bool(entry.get("pass")),
                      "why": str(entry.get("why", ""))[:300]})
    return clean, ""


def grade(item: dict, results: list[dict], error: str) -> list[dict]:
    """Pastikan setiap assertion dinilai; yang hilang dihitung gagal."""
    wanted = [str(a) for a in item.get("assertions", [])]
    by_text = {r["assertion"]: r for r in results}
    graded = []
    for assertion in wanted:
        if assertion in by_text:
            graded.append({"assertion": assertion, "pass": by_text[assertion]["pass"],
                           "why": by_text[assertion]["why"]})
        else:
            graded.append({"assertion": assertion, "pass": False,
                           "why": error or "judge tidak menilai assertion ini"})
    return graded


def run_one(item: dict, args, workdir: Path) -> dict:
    sandbox = Path(tempfile.mkdtemp(prefix=f"pakem-eval-{item.get('id')}-", dir=workdir))
    run = run_agent(args.agent_cmd, str(item.get("prompt", "")), sandbox, args.timeout)
    files = snapshot(sandbox)
    report = {"eval_id": item.get("id"), "sandbox": str(sandbox), "exit_code": run["exit_code"],
              "timed_out": run["timed_out"], "seconds": run["seconds"],
              "files_written": len(files), "judged": bool(args.judge_cmd),
              "stderr_head": run["stderr"].strip()[:300]}
    if args.judge_cmd:
        results, error = judge(args.judge_cmd, build_judge_payload(item, run, files), args.judge_timeout)
        graded = grade(item, results, error)
        report["results"] = graded
        report["passed"] = sum(1 for g in graded if g["pass"])
        report["total"] = len(graded)
        report["ok"] = report["passed"] == report["total"]
        if error:
            report["judge_error"] = error
    else:
        report["ok"] = None
        report["note"] = "tanpa --judge-cmd: transkrip direkam, assertion tidak dinilai"
    if args.keep or not args.judge_cmd:
        for name, text in (("stdout.txt", run["stdout"]), ("stderr.txt", run["stderr"]),
                           ("report.json", json.dumps({**report, "files": files}, ensure_ascii=False, indent=2))):
            (sandbox / name).write_text(text, encoding="utf-8")
    else:
        (sandbox.parent / f"{sandbox.name}.report.json").write_text(
            json.dumps({**report, "files": files}, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def select(doc: dict, wanted: list[str]) -> list[dict]:
    evals = doc["evals"]
    if not wanted:
        return evals
    chosen = []
    for token in wanted:
        for item in evals:
            if str(item.get("id")) == str(token):
                chosen.append(item)
                break
        else:
            raise SystemExit(f"eval {token} tidak ditemukan")
    return chosen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="run_evals", description="Jalankan evals Pakem.")
    parser.add_argument("--file", default=str(EVALS_FILE))
    parser.add_argument("--list", action="store_true", help="tampilkan eval yang tersedia")
    parser.add_argument("--validate", action="store_true", help="cek struktur evals.json")
    parser.add_argument("--eval", dest="only", action="append", default=[], help="id eval; dapat diulang")
    parser.add_argument("--agent-cmd", help="perintah agent; prompt dikirim lewat stdin")
    parser.add_argument("--judge-cmd", help="perintah penilai; menerima JSON di stdin")
    parser.add_argument("--timeout", type=int, default=600, help="batas detik per eval (default 600)")
    parser.add_argument("--judge-timeout", type=int, default=180)
    parser.add_argument("--workdir", help="direktori induk untuk sandbox (default: temp)")
    parser.add_argument("--keep", action="store_true", help="simpan sandbox beserta transkrip")
    parser.add_argument("--out", help="tulis laporan JSON ke path ini")
    parser.add_argument("--json", action="store_true", help="cetak laporan JSON ke stdout")
    args = parser.parse_args(argv)

    path = Path(args.file).expanduser()
    if not path.is_file():
        print(f"run_evals: {path} tidak ada", file=sys.stderr)
        return 2
    doc = load_evals(path)

    if args.validate or not (args.list or args.agent_cmd):
        problems = validate(doc)
        if problems:
            for problem in problems:
                print(f"[FAIL] {problem}")
            return 1
        print(f"evals: struktur sehat ({len(doc['evals'])} eval, "
              f"{sum(len(e['assertions']) for e in doc['evals'])} assertion)")
        if not (args.list or args.agent_cmd):
            print("Jalankan dengan --agent-cmd untuk mengeksekusi, atau --list untuk melihat daftar.")
            return 0

    if args.list:
        for item in doc["evals"]:
            prompt = " ".join(str(item["prompt"]).split())
            print(f"{str(item['id']):>3}  {prompt[:88]}")
        return 0

    workdir = Path(args.workdir).expanduser() if args.workdir else Path(tempfile.mkdtemp(prefix="pakem-evals-"))
    workdir.mkdir(parents=True, exist_ok=True)
    reports = [run_one(item, args, workdir) for item in select(doc, args.only)]

    if args.json:
        print(json.dumps({"workdir": str(workdir), "reports": reports}, ensure_ascii=False, indent=2))
    else:
        for report in reports:
            if report["judged"]:
                mark = "PASS" if report["ok"] else "FAIL"
                print(f"[{mark}] eval {report['eval_id']}: {report['passed']}/{report['total']} assertion "
                      f"(exit {report['exit_code']}, {report['seconds']}s)")
                for result in report["results"]:
                    if not result["pass"]:
                        print(f"        x {result['assertion']} — {result['why']}")
            else:
                print(f"[REKAM] eval {report['eval_id']}: exit {report['exit_code']}, "
                      f"{report['files_written']} file, {report['seconds']}s — assertion tidak dinilai")
            if report["timed_out"]:
                print("        ! agent timeout")
            elif report["exit_code"] not in (0, None) and report.get("stderr_head"):
                print(f"        ! agent exit {report['exit_code']}: {report['stderr_head']}")
        print(f"\nSandbox: {workdir}")

    if args.out:
        Path(args.out).write_text(json.dumps({"workdir": str(workdir), "reports": reports},
                                             ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.judge_cmd:
        return 0
    return 0 if all(report["ok"] for report in reports) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pre-publish gate: blocks personal identifiers, home paths, account ids, tokens and media metadata.

Three scans, each exits non-zero on a finding:

  --tree DIR            every text file under DIR (the working tree, or a site folder)
  --media DIR           every image and video under DIR: no EXIF/XMP/IPTC/C2PA/text chunks, no encoder or
                        creation_time tags, no GPS (needs Pillow; ffprobe for video)
  --git REVRANGE        every commit in the range (git log REVRANGE): author and committer email must be a
                        noreply address, the message and every ADDED line are scanned

  python3 prepublish_gate.py --tree . --media docs --git origin/main..HEAD
  python3 prepublish_gate.py --self-test        # plants one of each offender and checks the gate sees it

Secret VALUES are never printed: a match shows its first 4 characters then ***.
Personal identifiers are fully redacted, including commit email domains.
Allow a known-fake value by adding its exact text to scripts/lampway/pii_allow.txt (one per line, # comments), with the reason.
"""
import ast, fnmatch, io, os, re, subprocess, sys, json, tempfile, tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
OWNER = [s for s in os.environ.get("PII_OWNER_TERMS", "").split(",") if s]  # extra terms: names, handles, hostnames

# (id, severity, regex). Edit the OWNER terms through PII_OWNER_TERMS or the list below.
# Retain the original first dotted alphabetic-label admission, then consume the
# complete host so allow-list matching cannot accept a truncated domain prefix.
# Numeric version labels in prompt filenames are not admitted as email hosts.
PATTERNS = [
    ("owner-email", "HIGH", os.environ.get("PII_OWNER_EMAIL_RE") or r"(?!)"),
    ("any-email", "HIGH", r"(?<![\w.+-])[A-Za-z0-9._%+-]+@(?!(?:users\.noreply\.github\.com|example\.(?:com|invalid|org)|lampway\.(?:local|dev)|anthropic\.com)(?![\w.-]))[A-Za-z0-9-]+\.[A-Za-z]{2}[A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)*"),
    ("home-path", "MEDIUM", r"/(?:var/)?home/(?!user\b|you\b|runner\b|ubuntu\b|<)[a-z][a-z0-9_.-]*"),
    ("owner-username", "MEDIUM", os.environ.get("PII_OWNER_USER_RE") or r"(?!)"),
    ("owner-paths", "MEDIUM", os.environ.get("PII_OWNER_PATH_RE") or r"(?!)"),
    ("host-or-net", "MEDIUM", r"\.ts\.net\b|\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b|\b192\.168\.\d{1,3}\.\d{1,3}\b|\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    ("account-id", "HIGH", r"\buser_[A-Za-z0-9]{20,}|\boaiapp_[A-Za-z0-9]{16,}|\bapp_[A-Za-z0-9]{20,}"),
    ("signed-url", "CRITICAL", r"Key-Pair-Id=|X-Amz-Signature=|[?&]Signature=[A-Za-z0-9~_-]{16,}|Policy=eyJ"),
    ("openrouter-key", "CRITICAL", r"\bsk-or-v1-[A-Za-z0-9]{20,}"),
    ("api-key", "CRITICAL", r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{35}\b"),
    ("jwt", "CRITICAL", r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}"),
    ("bearer", "CRITICAL", r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{24,}"),
    ("private-key", "CRITICAL", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ("cloudfront-media", "HIGH", r"\b[a-z0-9]{10,}\.cloudfront\.net/[^\s\"']*"),
]
for t in OWNER:
    PATTERNS.append(("owner-term", "HIGH", r"(?i)" + re.escape(t)))
CP = [(i, s, re.compile(r)) for i, s, r in PATTERNS]

TEXT_EXT = (".py", ".md", ".txt", ".json", ".jsonl", ".html", ".css", ".js", ".mjs", ".ts", ".toml", ".yaml", ".yml", ".cfg", ".ini",
            ".sh", ".xml", ".svg", ".cmake", ".h", ".hh", ".cc", ".c", ".rs", ".env", ".csv", ".tsv", ".po", "")
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "locale"}      # locale: upstream translations, scanned by --git only
MEDIA_IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".tif", ".tiff", ".heic", ".ico")
MEDIA_VID = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".mp3", ".wav", ".m4a")
ALLOW = set()
ap = os.path.join(HERE, "pii_allow.txt")
if os.path.exists(ap):
    ALLOW = {l.split("#")[0].strip() for l in open(ap) if l.split("#")[0].strip()}

def mask(s):
    return s[:4] + "***"

def _native_matrix_operands(node):
    """Recognize Blender world-matrix multiplication of the same rig's bone head.

    MatMult syntax alone is insufficient: an unquoted email can also parse as
    name @ domain.attribute. Require the native pose-bone operand structure.
    """
    left, right = node.left, node.right
    if not (isinstance(left, ast.Attribute) and left.attr == "matrix_world"
            and isinstance(right, ast.Attribute) and right.attr == "head"
            and isinstance(right.value, ast.Subscript)):
        return False
    bones = right.value.value
    if not (isinstance(bones, ast.Attribute) and bones.attr == "bones"
            and isinstance(bones.value, ast.Attribute) and bones.value.attr == "pose"):
        return False
    return ast.dump(left.value) == ast.dump(bones.value.value)


def _python_matrix_at_columns(line):
    """Prove individual @ tokens are matrix operators in executable line syntax.

    Native-runner payloads contain indented Python inside multiline strings, so
    parse the line as a fragment. Quoted values, comments and incomplete syntax
    have no proven operator and remain subject to the email rule.
    """
    if "@" not in line or len(line.splitlines()) > 1:
        return set()
    offset = len(line) - len(line.lstrip(" \t"))
    code = line[offset:]
    try:
        tree = ast.parse(code)
        operators = [node for node in ast.walk(tree)
                     if isinstance(node, ast.BinOp) and isinstance(node.op, ast.MatMult)
                     and _native_matrix_operands(node)]
        columns = set()
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type != tokenize.OP or token.string != "@":
                continue
            # AST columns are UTF-8 bytes; tokenizer columns are characters.
            start = (token.start[0], len(code[:token.start[1]].encode("utf-8")))
            end = (token.end[0], len(code[:token.end[1]].encode("utf-8")))
            if any((node.left.end_lineno, node.left.end_col_offset) <= start
                   and end <= (node.right.lineno, node.right.col_offset)
                   for node in operators):
                columns.add(offset + token.start[1])
        return columns
    except (SyntaxError, ValueError, tokenize.TokenError, UnicodeError):
        return set()


def _allowed_email(value):
    """An email exemption covers its entire address or host, never a prefix."""
    host = value.rsplit("@", 1)[1]
    for allowed in ALLOW:
        if allowed == "@example":
            # Narrow the legacy RFC-example prefix to reserved exact hosts.
            if host in {"example.com", "example.org", "example.net", "example.test", "example.invalid"}:
                return True
        elif allowed.startswith("@"):
            if host == allowed[1:]:
                return True
        elif "@" in allowed and value == allowed:
            return True
    return False


def scan_line(line, source_path=None):
    # The default remains strict for commit messages and callers without a path.
    matrix_columns = (_python_matrix_at_columns(line)
                      if source_path and os.fspath(source_path).lower().endswith(".py") else set())
    out = []
    for pid, sev, rx in CP:
        for m in rx.finditer(line):
            v = m.group(0)
            if pid == "any-email" and m.start() + v.index("@") in matrix_columns:
                continue
            if (_allowed_email(v) if pid == "any-email"
                    else any(a and (a in v or a in line) for a in ALLOW)):
                continue
            out.append((pid, sev, mask(v) if sev == "CRITICAL" else "[redacted]"))
    return out

def scan_tree(root):
    findings = []
    for dp, dn, fs in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fs:
            p = os.path.join(dp, f)
            if not f.lower().endswith(TEXT_EXT) or f == "prepublish_gate.py" or f == "pii_allow.txt":
                continue
            try:
                if os.path.getsize(p) > 5_000_000:
                    continue
                with open(p, encoding="utf-8", errors="strict") as fh:
                    for n, line in enumerate(fh, 1):
                        for pid, sev, shown in scan_line(line, source_path=p):
                            findings.append((sev, pid, f"{os.path.relpath(p, root)}:{n}", shown))
            except (UnicodeDecodeError, OSError):
                continue
    return findings

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)

def scan_media(root):
    findings = []
    try:
        from PIL import Image
    except ImportError:
        Image = None
    for dp, dn, fs in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fs:
            p = os.path.join(dp, f); rel = os.path.relpath(p, root); lo = f.lower()
            if lo.endswith(MEDIA_IMG) and Image is not None:
                try:
                    im = Image.open(p); info = {k for k in im.info if k not in ("icc_profile", "loop", "background", "duration", "transparency", "dpi", "gamma", "chromaticity", "aspect", "jfif", "jfif_version", "jfif_unit", "jfif_density", "progressive", "progression", "srgb", "sizes", "compression")}
                    if len(im.getexif()):
                        findings.append(("MEDIUM", "media-exif", rel, "EXIF present"))
                    for k in info:
                        findings.append(("MEDIUM", "media-chunk", rel, f"metadata key {k}"))
                except Exception:
                    pass
                raw = open(p, "rb").read()
                if b"c2pa" in raw or b"jumb" in raw:
                    findings.append(("LOW", "media-c2pa", rel, "C2PA manifest (provenance; keep the 'AI-generated' disclosure in the caption if stripped)"))
                if b"<x:xmpmeta" in raw or b"photoshop:Credit" in raw:
                    findings.append(("MEDIUM", "media-xmp", rel, "XMP packet"))
            elif lo.endswith(MEDIA_VID):
                r = run(["ffprobe", "-v", "error", "-show_entries", "format_tags:stream_tags", "-of", "json", p])
                try:
                    j = json.loads(r.stdout or "{}")
                except ValueError:
                    j = {}
                tags = dict(j.get("format", {}).get("tags", {}))
                for s in j.get("streams", []):
                    tags.update({"s:" + k: v for k, v in s.get("tags", {}).items()})
                bad = {k: v for k, v in tags.items() if k.lower().lstrip("s:") not in ("major_brand", "minor_version", "compatible_brands", "language", "handler_name", "duration", "vendor_id") and not (k.lower() == "encoder" and v == "Lavf")}
                for k in bad:
                    findings.append(("MEDIUM", "media-tag", rel, f"container tag {k}"))
    return findings

def scan_git(rng):
    findings = []
    log = run(["git", "log", "--format=%H%x1f%ae%x1f%ce%x1f%an%x1f%cn%x1f%B%x1e", *rng.split()])
    if log.returncode:
        print(log.stderr, file=sys.stderr); sys.exit(2)
    for rec in log.stdout.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, ae, ce, an, cn, body = (rec.split("\x1f") + [""] * 6)[:6]
        for who, e in (("author", ae), ("committer", ce)):
            if not e.endswith("@users.noreply.github.com") and e not in ("noreply@anthropic.com", "noreply@github.com") and not e.endswith("@lampway.dev"):
                findings.append(("HIGH", "commit-email", f"{sha[:8]} {who}", "[redacted]"))
        for line in body.splitlines():
            for pid, sev, shown in scan_line(line):
                findings.append((sev, pid, f"{sha[:8]} message", shown))
    d = run(["git", "log", "-p", "--no-color", "--text", "--format=@@@%H", *rng.split()])
    cur = fil = None
    for line in d.stdout.splitlines():
        if line.startswith("@@@"):
            cur = line[3:11]; fil = None
        elif line.startswith("+++ "):
            fil = line[6:]
        elif line.startswith("+") and fil and not fil.startswith(("src/scripts/mixar/modules/common/i18n/locale/", "scripts/lampway/prepublish_gate.py", "scripts/lampway/pii_allow.txt")):   # the gate's own patterns and allow-list are not findings
            for pid, sev, shown in scan_line(line[1:], source_path=fil):
                findings.append((sev, pid, f"{cur} {fil}", shown))
    return findings

# Paths a commit may never ADD: a person's Lampway/Mixar home (chat history, checkpoints, operation history) or a test's unexpanded placeholder
# directory. A test once ran the binary with LAMPWAY_HOME="@RUN_TMP@/home" before the placeholder was expanded; it copied the person's real
# ~/.mixar into the repository and 436 private files were committed (purged before any push).
PRIVATE_PATHS = [
    (re.compile(r"^@[A-Z_]+@(/|$)"), "an unexpanded test placeholder directory"),
    (re.compile(r"(^|/)app/(chat_history|chat_media|checkpoints|operation_history|agent_history|scenes-dossier)/"), "a Lampway app home"),
    (re.compile(r"^(chat_history|chat_media|checkpoints|operation_history|agent_history|scenes-dossier)/"), "a home directory at the repository root"),
    (re.compile(r"^[^/]+\.mixar$"), "a .mixar file at the repository root"),
    (re.compile(r"(^|/)MIGRATED-FROM-MIXAR\.json$"), "a first-run migration marker (a copied home)"),
]


def scan_paths(rng, cwd=None):
    """Every file a commit in the range ADDS, held to PRIVATE_PATHS."""
    git = ["git"] + (["-C", cwd] if cwd else [])
    out = run(git + ["log", "--diff-filter=A", "--name-only", "--no-renames", "--format=@@@%H", *rng.split()])
    findings, cur = [], None
    for line in out.stdout.splitlines():
        if line.startswith("@@@"):
            cur = line[3:11]
        elif line.strip():
            for rx, what in PRIVATE_PATHS:
                if rx.search(line):
                    findings.append(("CRITICAL", "private-path", f"{cur} {line}", what))
                    break
    return findings


def report(findings, label):
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings = sorted(set(findings), key=lambda f: (order[f[0]], f[1], f[2]))
    for sev, pid, where, shown in findings[:300]:
        print(f"{sev:8} {pid:16} {where}  {shown}")
    if len(findings) > 300:
        print(f"... {len(findings) - 300} more")
    print(f"[{label}] {len(findings)} finding(s)")
    return findings

def self_test():
    with tempfile.TemporaryDirectory(dir=os.environ.get("GATE_TMP", HERE)) as d:
        planted = {
            "a.py": 'P = "/home/someone/projects/x"\n',
            "b.md": "mail me at someone@gmail.com\n",
            "c.json": '{"u": "user_ABCDEFGHIJKLMNOPQRSTUVWXYZ12"}\n',
            "d.txt": "https://x.example/a.fbx?Policy=eyJabc&Signature=" + "A" * 30 + "&Key-Pair-Id=K1\n",
            "e.txt": "key sk-or-v1-" + "a1" * 20 + "\n",
            "f.txt": "host box.tail1234.ts.net\n",
        }
        for n, t in planted.items():
            open(os.path.join(d, n), "w").write(t)
        f = scan_tree(d)
        ids = {x[1] for x in f}
        need = {"home-path", "any-email", "account-id", "signed-url", "openrouter-key", "host-or-net"}
        miss = need - ids
        for host in ("users.noreply.github.com", "example.com"):
            # Both independent exemption paths must reject a suffix lookalike.
            if not any(pid == "any-email" for pid, _, _ in
                       scan_line("noreply" + "@" + host + ".evil.org")):
                miss.add("email-domain-boundary")
        # media: a PNG with a text chunk
        try:
            from PIL import Image, PngImagePlugin
            im = Image.new("RGB", (4, 4)); pi = PngImagePlugin.PngInfo(); pi.add_text("Comment", "x")
            im.save(os.path.join(d, "g.png"), pnginfo=pi)
            if "media-chunk" not in {x[1] for x in scan_media(d)}:
                miss.add("media-chunk")
        except ImportError:
            print("Pillow missing: media self-test skipped")
        # a commit that adds a private home path
        repo = os.path.join(d, "repo")
        os.makedirs(os.path.join(repo, "@RUN_TMP@/home/app/chat_history"))
        open(os.path.join(repo, "@RUN_TMP@/home/app/chat_history/s.json"), "w").write("{}")
        open(os.path.join(repo, "ok.py"), "w").write("x = 1\n")
        g = ["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@users.noreply.github.com"]
        if run(["git", "init", "-q", repo]).returncode == 0 and run(g + ["add", "-A"]).returncode == 0 and run(g + ["commit", "-q", "-m", "x"]).returncode == 0:
            if "private-path" not in {x[1] for x in scan_paths("HEAD", cwd=repo)}:
                miss.add("private-path")
        else:
            miss.add("private-path (no git to plant a commit)")
        print("self-test:", "FAIL missing " + ",".join(sorted(miss)) if miss else "ok (every planted offender was seen)")
        return 1 if miss else 0

def main(argv):
    if "--self-test" in argv:
        return self_test()
    bad = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--tree": bad += report(scan_tree(argv[i + 1]), "tree"); i += 2
        elif a == "--media": bad += report(scan_media(argv[i + 1]), "media"); i += 2
        elif a == "--git": bad += report(scan_git(argv[i + 1]) + scan_paths(argv[i + 1]), "git"); i += 2
        else: print(__doc__); return 2
    blocking = [f for f in bad if f[0] != "LOW"]
    return 1 if blocking else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

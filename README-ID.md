<div align="center">

<img src="assets/banner.svg" alt="Pakem: Agent boleh ganti; pakem tetap." width="100%">

<br>

![protocol](https://img.shields.io/badge/protocol-v1.0-d4af37?style=flat-square&labelColor=0b0a14)
![python](https://img.shields.io/badge/python-3.10+-c9a7ff?style=flat-square&labelColor=0b0a14)
![deps](https://img.shields.io/badge/core-stdlib_only-ffb3d9?style=flat-square&labelColor=0b0a14)
![license](https://img.shields.io/badge/license-MIT-f3dd9a?style=flat-square&labelColor=0b0a14)

**Bahasa: [Bahasa Indonesia](README-ID.md) | [English](README.md)**

<a href="https://github.com/Matsumiko/pakem">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=20&pause=1200&color=FF8FB1&center=true&vCenter=true&width=700&lines=%E2%9C%A6+Lapisan+disiplin+kerja+untuk+agent+coding+%E2%9C%A6;Bukan+library%2C+bukan+framework.;Agent+boleh+ganti%3B+pakem+tetap.+%F0%9F%8C%B8" alt="animasi mengetik" />
</a>

<br>

Pakem bikin kerja agent **konsisten** 🌙, **bisa dilanjut** 🔁, dan **bisa dibuktikan selesai** ✅.

</div>

<img src="assets/divider.svg" alt="" width="100%">

## 📖 Daftar Isi

| Arc | Bab |
|---|---|
| 🌅 **Prolog** | [Masalah yang diselesaikan](#-prolog-masalah-yang-diselesaikan) |
| ⚔️ **Arc 1: Kebangkitan** | [Pasang](#-arc-1--kebangkitan-pasang) · [Pemakaian harian](#-arc-2--ritual-harian-pemakaian-harian) |
| 🔮 **Arc 2: Protokol** | [Protokol & antarmuka mesin](#-arc-3--protokol--antarmuka-mesin) · [Protokol stabil](#-protokol-operasi-stabil-pakem-10) · [MCP](#-adapter-mcp-mcp-2026-07-28) |
| 🛡️ **Arc 3: Penjaga** | [Worktree](#-isolasi-git-worktree) · [Runtime](#-runtime-otonom-v1-080) · [Peringatan perubahan aturan](#-peringatan-perubahan-aturan) |
| 📜 **Arc 4: Gulungan** | [Konfigurasi](#-konfigurasi-pakemprojectmd) · [Spec & plan](#-spec--plan-opsional) · [Sumber kebenaran](#-sumber-kebenaran-biar-tidak-duplikat) |
| 🔍 **Arc 5: Ujian** | [Audit](#-audit-artefak-pakem-audit) · [Gate](#-gate-pakem-finish-dan-pakem-check) · [Bukti](#-bukti----strict) |
| 🌌 **Arc 6: Kenaikan** | [Fondasi 1.1.0](#-fondasi-orkestrasi-produksi-110) · [Multi-agent](#-koordinasi-multi-agent-v090) |
| 🌙 **Epilog** | [Batasan](#-batasan-jujur) · [Peta jalan](#-peta-jalan) · [Lisensi](#-lisensi--distribusi) |

<img src="assets/divider.svg" alt="" width="100%">

## 🌅 Prolog: Masalah yang diselesaikan

> *Setiap pahlawan punya titik lemah. Ini yang dihadapi agent, dan apa yang Pakem pasang.* (◕‿◕)♡

| 💢 Masalah nyata | ✨ Yang Pakem pasang |
|---|---|
| Agent lupa konvensi project tiap sesi baru | `CONTEXT.md` (routing) + `PROJECT.md` |
| Kerja terputus di tengah jalan, besok mulai dari nol | `.pakem/sessions/*.json` dengan `lastPosition` + `nextStep` |
| Agent bilang "selesai" tapi belum tentu | `pakem finish`: gate yang bisa gagal (exit code 1) |
| Bug sama diperbaiki berkali-kali | `BUG-HISTORY.md` |
| Keputusan arsitektur diperdebatkan ulang | `DECISIONS.md` + `docs/adr/` |
| Claude, Cursor, Codex punya aturan beda-beda | adapter yang digenerate dari satu sumber |
| File project masih penuh placeholder | gate placeholder |
| Dokumen modul basi, menyebut file yang sudah dihapus | gate drift |
| Bingung file/dokumen apa yang perlu ada | `pakem audit`: REQUIRED / RECOMMENDED / NOT NEEDED, tanpa membuat file kosong |
| Agent langsung ngoding tanpa spec yang disetujui | `pakem spec` + `spec --approve`; gate `spec` |
| Pekerjaan besar tidak terpecah dan mudah melenceng | `pakem plan`: task 2–5 menit + files + verify; gate `plan` |
| Agent melebar: mengubah file di luar rencana | `pakem reconcile` + gate `scope` (kode di luar scope gagal; dokumentasi/config dilaporkan) |
| Spec "approved" padahal kriteria penerimaan belum terbukti | gate `acceptance` (saat `finish`) menolak kotak yang belum dicentang |
| Agent/tool perlu kontrak kerja yang sama | Pakem Protocol v1.0 + JSON Schema |
| Agent perlu konteks workflow tanpa parsing Markdown | `pakem context --json` |
| Gate bisa dijalankan CLI yang sudah diubah agent | manifest `pakem.py` + `pakem_core/*` dipin saat `start`; `pakem integrity` + `finish --strict` |
| Kunci seal hanya ada di satu host | `--key` / `PAKEM_SEAL_KEY` + `identity import` untuk host tanpa private key |
| HANDOVER.md terisi tapi isinya dari commit lama | cap HEAD + gate `handover`, `--check`/`--stamp` |
| Worktree menumpuk setelah task selesai | `plan done` membersihkan worktree yang merged & bersih, sisanya dilaporkan |
| Tidak ada angka kerja yang bisa dipertanggungjawabkan | `pakem report`: durasi, step, task, bukti verify, status ledger |
| Catatan sesi bisa disunting tanpa jejak | rantai hash (`events --verify`) + seal Ed25519 (`events --sign`) |
| Perubahan lintas modul sulit dipetakan | `pakem graph` + `pakem impact` |
| Riwayat lifecycle sulit diaudit lintas tool | event ledger append-only JSONL + `pakem events` |
| Workflow agent sulit distandarkan dan dipulihkan | `pakem runtime`: state machine, checkpoint, recovery metadata |
| Aksi berisiko perlu dibatasi lintas agent | `POLICY.json`, approval satu kali, lifecycle hooks |
| Beberapa agent mengerjakan proyek yang sama tanpa koordinasi | `pakem team`: task dependency, lease, handoff, shared board, independent review |
| Integrasi tool/model berubah-ubah | Pakem Protocol v1.0 stabil + negosiasi capability |
| Agent perlu tool interface universal | adapter MCP stateless stdio; default read-only, write tool diikat ke agent host |
| Agent mengubah file yang sama dari working tree bersama | isolasi Git worktree per task/agent; tanpa merge/push implisit |
| Agent melebar di dalam worktree, lalu di-merge | gate `worktree` + `pakem worktree scope` membandingkan diff worktree dengan scope task |
| Identitas agent hanya berupa ID metadata | identitas publik Ed25519, attestation bertanda tangan, revocation, dan delegation token ber-scope |
| Board/event lokal butuh transaksi state+audit yang atomik | Backend SQLite lokal dengan transaksi board+event dan backup online |
| Implementasi protocol perlu bukti kompatibilitas berulang | Pakem Conformance Profile v1 dengan test regresi |

<img src="assets/divider.svg" alt="" width="100%">

## ⚔️ Arc 1 · Kebangkitan (Pasang)

Folder ini adalah sebuah skill. Taruh sebagai `pakem/` di folder skill agent kamu (mis. `.claude/skills/pakem/` atau `~/.claude/skills/pakem/`). Untuk agent lain, cukup jalankan CLI-nya langsung.

Dengan Node 18+, paket npm memasang skill-nya untuk kamu (Pakem sendiri tetap butuh Python 3.10+):

```bash
npx pakem                          # ~/.claude/skills/pakem
npx pakem install --project        # ./.claude/skills/pakem
npx pakem install --dir ~/.agents/skills/pakem
```

Paket ini hanya menyalin skill; tidak menambah dependency npm ke proyekmu. Argumen lain diteruskan ke CLI Python bawaan paket (`npx pakem init --type app`).

Butuh **Python 3.10+**. CLI/Core dasar hanya memakai standard library. Operasi identitas Ed25519 opsional dan memerlukan `python -m pip install cryptography`.

```bash
cd proyek-kamu
python3 /path/ke/pakem/scripts/pakem.py init --type app
```

`--type`: `app` (default), `library`, `oneoff`, `research`.
Tambahan: `--verify "npm test && npm run lint"`, `--adapter claude,codex,cursor,gemini,copilot` (atau `none`), `--hook`.

Setelah init, CLI dan modul Pakem Core disalin ke `.pakem/` sehingga proyek mandiri. Modul Core dipisah dari CLI agar kemampuan intelligence bisa dipakai runtime lain.

<img src="assets/divider.svg" alt="" width="100%">

## 🍡 Arc 2 · Ritual Harian (Pemakaian harian)

```bash
python3 .pakem/pakem.py start "build a todo web app"      # or resume an interrupted session
python3 .pakem/pakem.py step "model done" --next "build the endpoint"
python3 .pakem/pakem.py adr "Choose SQLite"               # when an architecture decision appears
python3 .pakem/pakem.py bug "Crash on empty input" --symptom "..." --cause "..." --fix "..." --prevent "..."
python3 .pakem/pakem.py spec "Export feature"            # fill, then: pakem spec --approve
python3 .pakem/pakem.py plan add "write the parser" --files "src/parser.ts,tests/parser.test.ts" --verify "npm test -- parser"
python3 .pakem/pakem.py plan done T1     # runs the task verify + stores evidence
python3 .pakem/pakem.py audit                            # which files/docs are worth having (read-only)
python3 .pakem/pakem.py finish --summary "todo CRUD works, tests pass"   # add --fixed-bug / --strict when needed
```

**🗡️ Perintah lain:** `status`, `context --json`, `events --json`, `graph [--json]`, `impact --files FILE...`, `protocol info`, `protocol negotiate --peer-version 1.0`, `protocol validate-event FILE`, `protocol validate-session FILE`, `mcp serve`, `worktree create/list/scope/remove`, `events --verify/--sign`, `report [--json] [--session ID] [--limit N]`, `handover [--stamp] [--check]`, `integrity [--re-pin --reason ...]`, `worktree cleanup [--dry-run]`, `identity create/list/sign/verify/issue/rotate/revoke`, `team storage info/migrate/backup`, `check [--skip-verify]`, `audit [--json] [--strict]`, `spec`, `plan`, `handover`, `doctor`, `prune`, `ci`, `upgrade`, `adapt`, `hook install`, `runtime`, `policy`, `team`.

> 🪟 **Windows:** ganti `python3` dengan `python` atau `py -3`. Adapter dan `CONTEXT.md` sudah menjelaskan ini ke agent, dan git hook mencari interpreter yang benar-benar jalan. Dukungan Windows ditulis dengan hati-hati tapi **belum diuji di Windows**.

<img src="assets/divider.svg" alt="" width="100%">

## 🔮 Arc 3 · Protokol & Antarmuka Mesin

Pakem Protocol v1.0 memisahkan kontrak workflow dari CLI, model AI, bahasa, dan transport. Event envelope serta kompatibilitas session v1.0 dibekukan; fitur tambahan dinegosiasikan melalui capability. Spesifikasi dan JSON Schema ada di `.pakem/protocol/v1/`; source distribusi ada di `protocol/v1/`.

```bash
python3 .pakem/pakem.py protocol info
python3 .pakem/pakem.py protocol negotiate --peer-version 1.0 --capability events.v1 --capability context.snapshot.v1 --capability coordination.v1 --json
python3 .pakem/pakem.py context --json       # compact snapshot for agents/tools
python3 .pakem/pakem.py events --json        # structured event history
python3 .pakem/pakem.py events --verify      # verify the ledger hash chain
python3 .pakem/pakem.py events --sign --identity backend  # seal the ledger with Ed25519
python3 .pakem/pakem.py report --json       # roll-up of sessions, tasks, evidence, ledger
python3 .pakem/pakem.py events --session <session-id>
python3 .pakem/pakem.py protocol validate-event event.json
python3 .pakem/pakem.py protocol validate-session session.json

# Intelligent Core: dependency graph and change impact
python3 .pakem/pakem.py graph --json
python3 .pakem/pakem.py graph --json --output .pakem/dependency-graph.json
python3 .pakem/pakem.py impact --files src/auth.py tests/test_auth.py --json
python3 .pakem/pakem.py impact --base main --json
python3 .pakem/pakem.py impact --staged --strict --json
```

### 🕸️ Graph & Dampak

`pakem graph` membuat graph statis dari import lokal, termasuk alias `paths`/`baseUrl` di `tsconfig.json`/`jsconfig.json` (mengikuti `extends`, komentar JSONC diabaikan). Import yang tidak bisa di-resolve muncul di `unresolved_imports` beserta alasannya, dan siklus dependensi muncul di `circular_dependencies`. `pakem impact` menelusuri dependent langsung/transitif, test yang mungkin terdampak, dan sinyal risiko.

Analisisnya advisory dan best-effort: dynamic import, reflection, framework routing, code generation, dan runtime wiring bisa luput. `impact` menyertakan `graph_health`: kalau ada import yang tak ter-resolve, hasilnya ditandai belum lengkap dan rekomendasinya menyuruh memeriksa alias/baseUrl atau verifikasi manual. `--strict` mengembalikan exit 1 saat heuristik risiko HIGH; perintah ini tidak menjalankan test dan tidak menggantikan review atau verifikasi sebenarnya. Scanner bersifat read-only kecuali `graph --output` diminta eksplisit.

### 📼 Ledger Event

Lifecycle sesi dan task otomatis dicatat sebagai JSONL di `.pakem/events/` (lokal, di-gitignore secara default). Event dicatat append-only dan diserialisasi dengan lock Pakem. Ledger memudahkan audit/handover, tetapi **belum ditandatangani secara kriptografis** dan bukan bukti bahwa pekerjaan benar; hasil verify tetap disimpan terpisah sebagai evidence.

### 🧿 Snapshot Konteks

`context --json` memberikan project metadata, sesi aktif, progres spec/plan, hasil gate read-only (tanpa menjalankan verify), blocker, rekomendasi langkah berikutnya, dan status runtime/policy bila terpasang. Ia tidak mengirim isi source code, perintah verify, atau secret.

<img src="assets/divider.svg" alt="" width="100%">

## 🌠 Protokol Operasi Stabil (Pakem 1.0+)

Pakem Protocol v1.0 adalah kontrak stabil yang terpisah dari versi CLI, MCP, model, bahasa, dan provider. Bentuk event envelope serta aturan kompatibilitas session v1.0 dibekukan. Fitur baru dinyatakan melalui capability negotiation; capability bukan otorisasi untuk melakukan side effect.

```bash
python3 .pakem/pakem.py protocol info
python3 .pakem/pakem.py protocol negotiate --peer-version 1.0 \
  --capability events.v1 --capability context.snapshot.v1 --capability coordination.v1 --json
```

> ⚠️ `actor.name`, ID agent pada team board, dan MCP `clientInfo` adalah metadata atribusi. Ketiganya tidak membuktikan identitas. Host runtime wajib mengikat caller ke identitas tepercaya melalui boundary proses/credential/transport yang sesuai.

<img src="assets/divider.svg" alt="" width="100%">

## 🔌 Adapter MCP (MCP 2026-07-28)

Pakem menyertakan MCP server melalui stdio tanpa dependency eksternal. Adapter menargetkan MCP modern stateless: versi protokol dan client capabilities dikirim pada setiap request melalui `params._meta`; `server/discover` mengiklankan versi/capability, sedangkan `tools/list` dan `tools/call` menyediakan fungsi Pakem.

```bash
# Read-only, default
python3 .pakem/pakem.py mcp serve

# Board mutation only when the host explicitly grants agent binding and write access
python3 .pakem/pakem.py mcp serve --agent-id backend --allow-write
```

Read-only tools: context, Protocol info, team status/events, graph, impact, dan policy check. Mode write mengekspos claim, heartbeat, submit, review, dan assign sesuai role agent yang terdaftar. ID actor berasal dari `--agent-id` server, bukan argumen tool. Tool tidak menjalankan arbitrary shell, deployment, merge, push, atau policy change.

> ⚠️ `clientInfo` MCP adalah self-reported; keamanan binding hanya berlaku kalau host tepercaya meluncurkan proses dengan identitas dan hak akses yang benar. Jangan expose stdio server sebagai network service tanpa authz/authn tambahan.

<img src="assets/divider.svg" alt="" width="100%">

## 🌿 Isolasi Git Worktree

```bash
python3 .pakem/pakem.py worktree create T1 --agent backend --base main
python3 .pakem/pakem.py worktree list --json
python3 .pakem/pakem.py worktree scope T1--backend --strict
python3 .pakem/pakem.py worktree remove .pakem/worktrees/T1--backend
```

`worktree scope` membandingkan isi worktree (commit di branch, perubahan belum commit, dan file untracked) dengan `<task>` pada namanya. Gate `worktree` menjalankan pemeriksaan yang sama untuk semua worktree aktif saat `check`/`finish`; kode di luar scope di sana akan masuk ke branch yang nanti di-merge, jadi gate ini yang menutup celah "isolasi = aman".

Worktree diletakkan di `.pakem/worktrees/` dan branch bernama `pakem/<task>/<agent>`. Removal menolak worktree dirty kecuali `--force`; branch tidak dihapus otomatis. Fitur ini mengisolasi working tree, bukan melakukan task assignment, verification, merge, push, atau conflict resolution otomatis — pemeriksaan scope per worktree ada di `worktree scope`/gate `worktree`, sisanya tetap tanggung jawab operator.

<img src="assets/divider.svg" alt="" width="100%">

## 🤖 Runtime Otonom v1 (0.8.0)

`pakem init` memasang `.pakem/POLICY.json`, Runtime/Policy schemas, dan modul Core runtime. State workflow lokal disimpan di `.pakem/runtime/` dan diabaikan Git secara default.

```bash
# Start and monitor the runtime workflow
python3 .pakem/pakem.py runtime init "implementasi OAuth"
python3 .pakem/pakem.py runtime status --json
python3 .pakem/pakem.py runtime transition ready --reason "spec dan plan disetujui"
python3 .pakem/pakem.py runtime transition executing --task-id T1

# Checkpoint and recovery metadata
python3 .pakem/pakem.py runtime checkpoint --label "sebelum refactor" --json
python3 .pakem/pakem.py runtime recover --json

# Lifecycle hooks and policy
python3 .pakem/pakem.py runtime hook task.before --payload-file action.json --json
python3 .pakem/pakem.py policy show --json
python3 .pakem/pakem.py policy check --category deploy --risk high --target staging --json
python3 .pakem/pakem.py policy approve --category deploy --risk high --target staging --reason "user approved staging"
```

State machine membatasi transisi ilegal. Checkpoint menyimpan metadata workflow dan snapshot HEAD/status Git. `recover` hanya mengembalikan metadata workflow ke state `recovering`; ia **tidak** melakukan checkout, reset, revert, atau mengubah source code. Selalu tinjau Git diff sebelum melanjutkan.

**🎚️ Mode policy**

| Mode | Perilaku |
|---|---|
| `manual` | meminta approval untuk semua aksi selain read |
| `assisted` | mengizinkan edit biasa, tetapi meminta approval untuk command medium/high dan kategori sensitif |
| `guarded_autonomous` | mengizinkan aksi hingga `maxAutonomousRisk`, kecuali kategori yang selalu memerlukan approval |

`deniedCategories` tetap ditolak meskipun ada approval.

Approval lokal bersifat satu kali, kedaluwarsa, dan terikat pada workflow, kategori, tingkat risiko, serta target. Ini **bukan autentikasi manusia yang aman**: CLI tidak dapat membuktikan siapa yang menjalankan `policy approve`. Host agent wajib menghentikan aksi dan meminta konfirmasi user melalui kanal tepercaya; agent tidak boleh menyetujui dirinya sendiri. Jangan memasukkan secret atau perintah lengkap ke target/payload hook.

**🪝 Hook standar:** `session.start`, `task.before`, `task.after`, `verification.before`, `session.finish`, `handover`. `runtime hook` mengembalikan `allow`, `require_approval`, atau `deny` dan mencatat receipt tanpa menyimpan payload mentah. Host runtime wajib menegakkan keputusan ini; Pakem tidak mengeksekusi command, deploy, atau agent.

<img src="assets/divider.svg" alt="" width="100%">

## 🚨 Peringatan perubahan aturan

Gate bisa dilewati kalau agent diam-diam melonggarkan aturannya. Karena itu `start` menyimpan potret `rule.*`, `verify`, `sensitive`, `exposure`, `deploy`, `handover`, dan manifest hash `.pakem/pakem.py` beserta seluruh `.pakem/pakem_core/*.py`. Di `check`, `finish`, dan `audit`, perubahan setelahnya muncul sebagai:

```
[WARN] rules-changed: rule.tests relaxed: required -> skip
[WARN] rules-changed: verify changed: 'npm test' -> 'true'
[WARN] rules-changed: exposure downgraded: public -> private
[WARN] rules-changed: deploy downgraded: production -> none
[WARN] rules-changed: .pakem/pakem.py modified during this session
```

`finish` juga mencetak gap berisiko menurut flag:

```
[WARN] risk: deploy=production but no CI yet
[WARN] risk: deploy=production but no RUNBOOK.md yet
WARNING: 2 risks unresolved (advisory, non-blocking).
```

Ini tidak memblokir (kadang perubahan memang diminta user), tapi tercatat di sesi dan agent diwajibkan melaporkannya. Pakem membuat pelonggaran *kelihatan*; ia tidak bisa mencegah agent yang bertekad menipu.

<img src="assets/divider.svg" alt="" width="100%">

## 🧭 Cek kondisi repo saat resume

Di setiap `start` dan `step`, Pakem mencatat commit HEAD dan daftar file yang berubah (di luar `.pakem/`). Saat `start` menemukan sesi terputus, ia membandingkan dengan kondisi sekarang:

```
CHECK: repo state changed since the last record:
  - HEAD changed (2 new commits)
  - changed since the last record: M src/api.py; ?? scratch.txt
```

Jadi `nextStep` yang basi atau kerja yang belum sempat dicatat langsung terlihat. Hanya aktif di repo git.

File sesi ditulis atomik (tulis ke file sementara, `fsync`, lalu rename), sehingga listrik mati di tengah penulisan tidak meninggalkan JSON setengah. Semua tulisan `.pakem/*.md`/ADR/BUG-HISTORY juga memakai jalur atomik, dan mutasi sesi/dokumen dikunci antar-proses (`pakem_lock`). Kalau tetap ada file sesi yang korup, `status`/`start`/`check`/`finish` menampilkan `[WARN] corrupt session ignored: ...` — tidak lagi hilang diam-diam.

<img src="assets/divider.svg" alt="" width="100%">

## 🏯 Apa yang dibuat `init`

```
.pakem/
├── CONTEXT.md        entry point + routing: read this first
├── PROJECT.md        config (verify, rule.*) + stack + conventions
├── MODULE-MAP.md     module map (app/library)
├── DECISIONS.md      decision index (app/library/research)
├── BUG-HISTORY.md    bug history (app/library)
├── pakem.py          standalone CLI per project
├── POLICY.json       autonomy and approval policy (project-managed)
├── pakem_core/       Core modules (intelligence + autonomous runtime)
├── protocol/v1/      event/session contract
├── intelligence/v1/  graph/impact output schemas
├── runtime/v1/       workflow/checkpoint/lifecycle hook schemas
├── policy/v1/        policy schema
├── sessions/         per-session JSON (gitignored by default)
├── events/           local event ledger (gitignored by default)
└── runtime/          workflow, checkpoints, approvals, hook receipts (gitignored)
docs/adr/             only when the adr rule is active (new project)
tests/                only when tests rule = required (new project)
CLAUDE.md, AGENTS.md, .cursor/rules/pakem.mdc   adapters (marked blocks, existing content preserved)
```

**Scaffolding bersyarat:** `oneoff` hanya dapat `CONTEXT.md` dan `PROJECT.md`. Repo yang sudah ada terdeteksi otomatis dan **tidak dirombak**; hanya `.pakem/` dan adapter yang ditambah.

<img src="assets/divider.svg" alt="" width="100%">

## 📜 Konfigurasi (`.pakem/PROJECT.md`)

Bagian atas file berisi konfigurasi, satu `key: value` per baris:

```
type: app
sensitive: false
exposure: private
deploy: none
handover: false
verify: npm test && npm run lint
rule.tests: required
rule.adr: when-decision
rule.research: skip
reason.research: stack sudah ditentukan user, tidak ada eksplorasi
rule.modular: required
```

Nilai `rule.*`: `required`, `skip`, `when-decision`, `when-needed`. Setiap `skip` **wajib** punya `reason.*`. Gate tidak gagal karena folder tidak ada, tapi gagal kalau aturan dilewati diam-diam.

**🚩 Flag risiko** (dibaca `pakem audit`, bukan gate):

| Flag | Nilai | Efek pada audit |
|---|---|---|
| `exposure` | `private` / `public` | publik → saran LICENSE, CONTRIBUTING, SECURITY, template PR/issue |
| `deploy` | `none` / `staging` / `production` | deploy → saran CI, DEPLOYMENT, RUNBOOK |
| `handover` | `true` / `false` | true → saran HANDOVER, akses, known issues, tech debt |
| `sensitive` | `true` / `false` | true → saran SECURITY, threat model, secret scan |

`start` memotret keempat flag ini; menurunkannya saat sesi berjalan memunculkan `[WARN] rules-changed`. Audit tetap read-only dan tidak pernah membuat file.

<img src="assets/divider.svg" alt="" width="100%">

## 📝 Spec & plan (opsional)

Untuk fitur/perubahan multi-file, jangan langsung ngoding. Untuk typo atau edit satu file, lewati.

```bash
python3 .pakem/pakem.py spec "Export feature"     # create .pakem/SPEC.md
# fill Problem / Non-goals / Acceptance / Approach
python3 .pakem/pakem.py spec --approve          # all [FILL] placeholders must be filled

python3 .pakem/pakem.py plan add "write the parser" \
  --files "src/parser.ts,tests/parser.test.ts" \
  --verify "npm test -- parser"
python3 .pakem/pakem.py plan list
python3 .pakem/pakem.py plan done T1     # runs the task verify + stores evidence
python3 .pakem/pakem.py plan drop T2 --reason "no longer relevant"
```

- 📄 `SPEC.md` berstatus `draft` sampai `spec --approve`; selama draft, `check`/`finish` gagal di gate `spec`.
- 🗒️ Setiap task berisi `files` dan `verify`; selama ada `[ ]`, `check`/`finish` gagal di gate `plan`. `plan drop` menandai task selesai dengan alasan.
- ✅ Bagian Acceptance `SPEC.md` harus dicentang (`- [x]`) sebelum `finish` lolos gate `acceptance`; `check` hanya menagih approval, karena spec disetujui sebelum kerja dimulai.
- 🧾 Setiap task `[x]` harus punya bukti verify yang masih berlaku: `plan done` menjalankan `--verify` task itu dan mencatat exit code, hash output, serta sidik file scope di `.pakem/verify/tasks.json`. Kalau file scope berubah setelah verify, gate `task-verify` menolak sampai bukti diperbarui. Pengecualian harus eksplisit: `--no-verify --reason "..."`, dan waiver itu selalu disebut di baris gate. Task yang di-drop tidak diklaim selesai, jadi tidak menuntut bukti.
- 🎯 Perubahan **kode** di luar `--files` seluruh task menggagalkan gate `scope`; file non-kode (dokumen, config, lockfile) hanya dilaporkan. Patokannya HEAD saat sesi `start`, jadi perubahan yang sudah di-commit dan file yang dihapus tetap terlihat — `git diff HEAD` saja tidak cukup. `pakem reconcile` memperlihatkan keduanya sebelum `finish`.
- 🌿 Gate `worktree` mengulang pemeriksaan itu untuk tiap worktree terkelola: diff branch + perubahan belum commit + file untracked dibandingkan dengan scope task pada nama worktree, dan task tanpa scope file juga dilaporkan.
- ⏱️ Target task: 2–5 menit, satu perubahan kecil yang bisa diverifikasi.
- 👀 `start`/`status` menampilkan status spec dan progres plan; `doctor` memperingatkan kalau masih draft/pending.

<img src="assets/divider.svg" alt="" width="100%">

## 🗝️ Sumber kebenaran (biar tidak duplikat)

| File | Peran | Jangan taruh |
|---|---|---|
| `PROJECT.md` | fakta + config proyek (`verify`, `rule.*`, flag) | riwayat task |
| `CONTEXT.md` | routing: baca apa dulu; protokolnya digenerate | spesifikasi fitur |
| `SPEC.md` | kenapa/apa + acceptance untuk satu pekerjaan | daftar task |
| `PLAN.md` | urutan task (how) untuk pekerjaan itu | masalah/non-goal |
| session JSON | apa yang benar-benar terjadi (`steps`, `nextStep`) | niat/rencana |
| `MODULE-MAP.md` | struktur modul | status pekerjaan |
| `DECISIONS.md` + `docs/adr/` | index + detail keputusan | bug/riwayat kerja |
| `BUG-HISTORY.md` | bug yang sudah diperbaiki | bug yang masih terbuka |
| `HANDOVER.md` | snapshot akhir: akses, kontak, sisa kerja, risiko | password/secret |
| `references/` | panduan generik | fakta spesifik proyek |

Aturan: **jangan menyalin isi**, tunjuk file sumbernya. `CONTEXT.md` dan adapter memakai protokol yang digenerate dari satu sumber; `pakem upgrade` menyinkronkan bloknya, `doctor` memperingatkan kalau basi.

| Perintah | Peran |
|---|---|
| `status` | ringkasan read-only |
| `check` | gate yang bisa gagal |
| `reconcile` | laporan read-only: perubahan Git vs scope task (plan/board) vs acceptance (`--json`, `--strict`) |
| `finish` | gate + bukti verify + tutup sesi |
| `audit` | inventaris artefak, advisory |
| `doctor` | diagnosis setup (config/git/hook/adapter/sesi) |
| `spec` / `plan` | state workflow, bukan gate verifikasi |

<img src="assets/divider.svg" alt="" width="100%">

## 🔍 Audit artefak (`pakem audit`)

Pakem tidak mengejar kelengkapan file. `audit` memilah artefak berdasarkan `type`, `exposure`, `deploy`, `handover`, `sensitive`, dan isi repo:

```
AUDIT  your-project
configuration: type=app exposure=private deploy=none handover=false sensitive=false

REQUIRED - continuity & verification
  [ok]  README.md
  [gap] verify — fill in the test/lint/build command
  [gap] tests/ — logic needs tests run by verify

RECOMMENDED - risk-based; may be deferred with a reason
  [gap] .env.example — code reads the environment
  ...

NOT NEEDED - do not create just for completeness
  [-]   LICENSE — private repo; change exposure: public if it will be released
  [-]   docs/decisions/ — canonical: docs/adr/ — do not keep both
  ...
```

- 👁️ `audit` **read-only**: tidak membuat file, tidak mengubah konfigurasi.
- 🤖 `--json` untuk agent; `--strict` exit 1 bila ada REQUIRED yang kurang.
- 🕰️ Yang RECOMMENDED boleh ditunda dengan alasan jujur; jangan membuat file kosong.
- 🎬 `init` langsung mencetak ringkasan rencana artefak.
- ⚠️ `finish` mencetak `[WARN] risk: ...` untuk gap yang flag-nya aktif (mis. `deploy=production but no RUNBOOK.md yet`). Ini **advisory**: tidak mengubah exit code, tapi wajib dilaporkan.
- 📦 `pakem handover` membuat **satu** `HANDOVER.md` (status, akses tanpa password, kontak, sisa kerja, risiko). Placeholder-nya ikut ditolak gate sampai diisi; jangan memecahnya menjadi `ACCESS` + `KNOWN_ISSUES` + `TECH_DEBT` + `HANDOVER` yang cepat basi.
- 📚 Detail per mode kegagalan, pilihan kanonik (mis. `docs/adr/` bukan `docs/decisions/`), dan daftar yang tidak boleh dibuat otomatis: `references/artifacts.md`.

<img src="assets/divider.svg" alt="" width="100%">

## 🩺 Diagnosis & perawatan

```bash
python3 .pakem/pakem.py doctor            # check config, placeholders, git, hooks, adapters, sessions
python3 .pakem/pakem.py doctor --verify   # also run the verify command
python3 .pakem/pakem.py prune             # dry-run: show old sessions that can be pruned
python3 .pakem/pakem.py prune --yes       # delete; active sessions and the newest N are kept
python3 .pakem/pakem.py ci                # create .github/workflows/ci.yml
# Run the newest CLI from the skill install, from the project root (including upgrades from 0.6.x)
python3 /path/ke/pakem/scripts/pakem.py upgrade --dry-run
python3 /path/ke/pakem/scripts/pakem.py upgrade
```

- 🩹 `doctor` exit 1 bila ada **FAIL** (config rusak, verify kosong, placeholder tersisa, sesi korup); WARN hanya saran. `--json` untuk agent. Ia juga memperingatkan SPEC draft dan PLAN yang masih punya task terbuka.
- 🧹 `prune` default `--keep 20 --days 90`; sesi aktif tidak pernah dihapus, sesi korup tidak disentuh.
- 🏗️ `ci` mendeteksi Node (npm/pnpm/yarn), Python, Go, atau Rust lalu menjalankan `pakem check` — jadi `verify` tetap satu sumber kebenaran. `--force` menimpa workflow yang sudah ada.
- ⬆️ `upgrade` memperbarui CLI, modul Core, schema protocol/intelligence, flag baru, `.gitignore`, dan adapter. Isi manual dokumen proyek (termasuk `MODULE-MAP.md`/ADR) dipertahankan; hanya blok protokol Pakem yang memang ditandai di `CONTEXT.md`/adapter disinkronkan. Jalankan `--dry-run` dulu dan gunakan CLI terbaru dari instalasi skill.

<img src="assets/divider.svg" alt="" width="100%">

## 🧪 Bukti & `--strict`

`finish` menyimpan bukti verify di sesi (`verifyEvidence`): perintah, exit code, durasi, hash output, dan hash `.pakem/pakem.py`; saat dijalankan ia mencetak:

```
[EVIDENCE] verify: pass exit=0 hash=4355a46b19d348dc
```

Default `finish` tetap advisory: gap audit REQUIRED muncul sebagai `[WARN] required: ...`. Tambah `--strict` bila ingin sesi **gagal** ketika aturan/CLI berubah, `verify` bukan `pass`, atau ada gap audit REQUIRED. Ini yang membuat "selesai" lebih sulit dibohongi, bukan sekadar exit 0.

<img src="assets/divider.svg" alt="" width="100%">

## 👓 Lensa review

`references/reviews.md` memuat lensa frontend (konsistensi komponen/token, state loading/empty/error, responsif, a11y) dan backend (otorisasi server-side, validasi batas, query parameterized, secret, PII, fail closed). Dibaca sebelum `finish` bila proyek punya UI atau `sensitive: true`; bukan gate, dan tidak menggantikan review manusia.

<img src="assets/divider.svg" alt="" width="100%">

## 🚪 Gate (`pakem finish` dan `pakem check`)

| Gate | Gagal bila |
|---|---|
| session | (hanya `finish`) tidak ada sesi aktif atau `--summary` kosong |
| bug | (hanya `finish --fixed-bug`) belum ada entri `pakem bug` di sesi ini |
| rules | `required` tak terpenuhi, atau `skip` tanpa alasan |
| placeholder | sisa `[FILL`, `[ISI` (lama), `{{...}}`, `TODO` di `.pakem/*.md` dan `docs/adr/*.md` |
| spec | `.pakem/SPEC.md` ada tapi belum `approved` |
| plan | `.pakem/PLAN.md` ada tapi masih ada task `[ ]` |
| drift | path di backtick pada MODULE-MAP/DECISIONS tidak ada di repo |
| verify | perintah `verify` exit non-nol, atau kosong tanpa `reason.verify` |

Exit code 1 bila ada yang gagal. Gate verify menjalankan test/lint/build **milik proyek kamu**: Pakem tidak menggantikan test, ia memaksa test dijalankan. `[WARN] risk:` dari audit tidak mengubah exit code.

<img src="assets/divider.svg" alt="" width="100%">

## 🛡️ Enforcement

- **Git pre-commit:** `python3 .pakem/pakem.py hook install` (tambah `--skip-verify` bila test terlalu lambat untuk tiap commit). Hook dipasang di folder yang benar-benar dibaca git, jadi `core.hooksPath` dan worktree ikut didukung.
- **Agent:** adapter menyuntikkan protokol ke `CLAUDE.md`, `AGENTS.md`, dll. Untuk Claude Code kamu juga bisa memasang hook Stop yang menjalankan `check`; cek dokumentasi versi yang kamu pakai untuk format terbarunya.

<img src="assets/divider.svg" alt="" width="100%">

## 🧫 Tes

Suite penuh butuh dua dependency opsional (dipakai satu modul tes untuk Ed25519 dan satu untuk validasi JSON Schema):

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
```

Tanpa dependency itu suite tetap jalan dan hijau; 14 tes melompat dengan alasan yang terlihat di output.

Eval perilaku skill (bukan kode) dicek terpisah:

```bash
python3 scripts/run_evals.py --validate     # struktur evals.json
python3 scripts/run_evals.py --list         # 24 eval
```

Menjalankan eval butuh perintah agent dan perintah judge; kontraknya di `evals/README.md`.

<img src="assets/divider.svg" alt="" width="100%">

## 🌌 Fondasi Orkestrasi Produksi (1.1.0)

Pakem 1.1 menambahkan dua fondasi untuk koordinasi yang lebih kuat. Keduanya opt-in dan menjaga kompatibilitas default versi sebelumnya.

### 🔑 Identitas agent Ed25519

Public key identitas disimpan dan bisa dibagikan lewat `.pakem/identity/registry.json` (metadata publik); private key disimpan di direktori konfigurasi user (`$XDG_CONFIG_HOME/pakem/identities/` pada Linux/macOS atau `%APPDATA%/Pakem/identities/` pada Windows), bukan di repository. File private key ditulis dengan permission owner-only bila OS mendukung.

```bash
# Needs the optional dependency: python -m pip install cryptography
python3 .pakem/pakem.py identity create backend
python3 .pakem/pakem.py identity list --json
python3 .pakem/pakem.py identity sign backend --file receipt.json --output receipt.signed.json
python3 .pakem/pakem.py identity verify receipt.signed.json
python3 .pakem/pakem.py identity rotate backend --reason "scheduled key rotation"

# Delegation tokens are limited by audience, action, and lifetime (30 seconds–24 hours)
python3 .pakem/pakem.py identity issue backend \
  --audience pakem-host://worker-01 \
  --action team.claim --action team.submit --ttl-seconds 900 > delegation.json
python3 .pakem/pakem.py identity verify delegation.json \
  --audience pakem-host://worker-01 --action team.claim

python3 .pakem/pakem.py identity revoke backend --reason "agent retired"
```

`identity rotate` membuat keypair baru dan mempertahankan public metadata key lama sebagai retired; signature lama tidak lagi diterima sebagai identitas aktif. Signature memverifikasi bahwa payload tidak berubah dan ditandatangani oleh private key yang cocok dengan public registry. Delegation token memeriksa subject, audience, action, expiry, dan revocation.

> ⚠️ **Ini bukan autentikasi transport atau sandbox**: token tetap bearer credential dan dapat di-replay selama masih valid. Host harus mengikat token ke koneksi/proses caller, membatasi audience/actions, mengatur anti-replay, menjaga waktu sistem, serta melindungi registry dan private key. Mengganti project path akan menghasilkan namespace private-key yang berbeda; provisioning key untuk host lain harus dilakukan melalui kanal aman.

### 🗄️ Backend koordinasi SQLite

JSON board + JSONL tetap menjadi default agar project lama tidak berubah. Migrasi hanya dilakukan dengan tindakan eksplisit:

```bash
python3 .pakem/pakem.py team storage info
python3 .pakem/pakem.py team storage migrate --to sqlite
python3 .pakem/pakem.py team storage info --json
python3 .pakem/pakem.py team storage backup --output backups/pakem-team.sqlite3
```

SQLite menyimpan board dan event ledger; setiap mutasi memperbarui keduanya dalam satu transaksi. File `board.json` dan `events.jsonl` asli dipertahankan sebagai backup dan tidak diperbarui lagi setelah SQLite menjadi authoritative. Backup online memakai SQLite backup API agar menghasilkan snapshot konsisten.

**Batas backend:** SQLite ini tetap lokal ke project directory dan bergantung pada locking SQLite/filesystem yang benar. Jangan mengandalkannya sebagai distributed database atau menaruh WAL database pada filesystem jaringan yang tidak menjamin locking. Koordinasi multi-host membutuhkan service backend terautentikasi tersendiri, yang belum disediakan release ini.

### 📋 Profil conformance

`conformance/v1/README.md` mendefinisikan kewajiban implementasi dan batas klaim conformance. Test executable ada di `tests/test_release_110.py`. Kelulusan test tidak membuktikan transport authentication, process isolation, distributed consensus, atau kebenaran hasil kerja agent.

<img src="assets/divider.svg" alt="" width="100%">

## 👥 Koordinasi Multi-Agent (v0.9.0+)

Pakem dapat mengelola shared task board untuk agent kooperatif: registrasi role/capability, task yang sadar dependency, assignment, lease eksklusif yang kedaluwarsa, heartbeat, release, handoff, submission dengan evidence reference, dan review independen. State disimpan di `.pakem/team/`; lock file menserialisasi operasi lintas proses pada filesystem lokal.

```bash
pakem team init
pakem team register lead --role lead
pakem team register backend --role worker --capability python --capability api
pakem team register reviewer --role reviewer
pakem team add T1 --title "Implement API" --files src/api.py tests/test_api.py --risk medium --capability python
pakem team assign T1 --agent backend --by lead
pakem team claim T1 --agent backend
pakem team heartbeat T1 --agent backend
pakem team submit T1 --agent backend --summary "API implemented and tested" --evidence tests/test_api.py --evidence commit:abc123
pakem team review T1 --reviewer reviewer --decision approve
pakem team status --json

# optional: bind the action to an Ed25519 identity and prove the board was not altered
pakem team submit T1 --agent backend --summary "API implemented" --evidence tests/test_api.py --sign
pakem team review T1 --reviewer reviewer --decision approve --sign
pakem team verify --json
```

Task tetap di `review` sampai reviewer lain menyetujuinya. Dependency baru bisa di-claim setelah task induknya `done`. Claim yang kedaluwarsa bisa diambil ulang. ID/role agent adalah metadata kooperatif, bukan autentikasi; host tepercaya harus mengikat identitas caller yang terautentikasi ke `--agent`.

Dengan identitas Ed25519 terpasang, `team register` mengikat fingerprint-nya ke board, `--sign` menyegel setiap payload submission dan review, dan `pakem team verify` memeriksa signature, status revocation, serta apakah board masih cocok dengan yang ditandatangani: tamper-evident, bukan autentikasi transport. Pakem tidak spawn agent, menjalankan command, mem-sandbox scope file, merge branch, atau menyediakan distributed consensus. Event ledger koordinasi adalah receipt audit, bukan bukti bahwa evidence sudah diverifikasi secara independen. Lihat `.pakem/coordination/v1/README.md` untuk lifecycle dan batas kepercayaan.

<img src="assets/divider.svg" alt="" width="100%">

## 🌙 Batasan jujur

> *Bahkan protagonis terkuat punya batas. Lebih baik tahu lebih awal.* (´･ω･`)

- Bukan pengganti test: gate memaksa test jalan, bukan menjamin test-nya bagus.
- Bukan sandbox: agent tetap bisa mengabaikan instruksi. Hook dan exit code mempersempit celahnya, tidak menutupnya.
- Bukan memori semantik/vector: ini file terstruktur yang bisa dibaca dan di-diff.
- Koordinasi multi-agent bersifat lokal: Pakem menyediakan shared board, lease, handoff, dan independent review, tetapi belum spawn agent, menjalankan command, merge branch, atau menyediakan distributed consensus. Isolasi direktori kerja tersedia lewat `pakem worktree` (Git worktree lokal); merge/push tetap tanggung jawab operator.
- Pakem Protocol v1.0 menyediakan JSON/JSONL contract, CLI validator, dan MCP stdio adapter lokal (read-only secara default); transport remote dan SDK lintas bahasa tidak disediakan.
- Event ledger bersifat append-only pada jalur CLI, tetapi bukan storage immutable: pengguna dengan akses filesystem tetap dapat mengubahnya.
- Gate drift hanya memeriksa path di backtick; bukan analisis kode. Dependency graph/impact menambah analisis import statis, tetapi belum mencakup seluruh hubungan runtime.
- `audit` menilai keberadaan artefak dan flag risiko, bukan kualitas isinya. Deteksi env/CI/lockfile berbasis pola file, bukan analisis mendalam.
- Bukti `verifyEvidence` membuktikan perintah dijalankan dan exit/hash-nya, bukan bahwa test-nya cukup atau benar.
- Lock antar-proses bergantung pada `flock`/`msvcrt`; perilaku di NFS, container read-only, dan Windows belum diuji.
- `SPEC.md` dan `PLAN.md` adalah penanda lokal: `spec --approve` / `plan done` bisa diubah agent. Pakem membuatnya terlihat dan digate, bukan menandatanganinya secara kriptografis.
- Pakem menyediakan wadah spec dan aturan bertanya; ia bukan interviewer otomatis yang menanyakan satu per satu bagian spec.

<img src="assets/divider.svg" alt="" width="100%">

## 🌸 Peta jalan

- [ ] Runtime lifecycle hooks universal (Stop/AfterTool sesuai kemampuan host agent)
- [ ] Context retrieval yang memanfaatkan graph, MODULE-MAP, symbol index, dan hasil pekerjaan sebelumnya
- [ ] Impact analysis lebih dalam (AST/symbol-level, framework routing, path alias, generated code) dan pemicu otomatis dari workflow hooks
- [ ] Evidence ledger yang dapat diverifikasi/ditandatangani dan provenance perubahan
- [ ] Policy engine + guarded autonomy dengan approval untuk operasi berisiko
- [ ] MCP HTTP transport dan SDK referensi untuk Python/TypeScript
- [ ] Authenticated agent identity, remote coordination adapter/database backend, dan conflict-aware merge orchestration
- [ ] Documentation drift dan audit lebih dalam untuk API/DB/infra
- [ ] Template CI untuk GitLab/CircleCI selain GitHub Actions

<img src="assets/divider.svg" alt="" width="100%">

## 📦 Lisensi & distribusi

MIT — lihat `LICENSE`.

Struktur mengikuti format Agent Skills/skill-creator: `SKILL.md`, `assets/templates/`, `references/`, `scripts/`, `evals/`, dan `tests/`. Isi `evals/` dijalankan dengan `python3 scripts/run_evals.py` (lihat `evals/README.md`). Validasi dan paket:

```bash
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py .
python3 ~/.agents/skills/skill-creator/scripts/package_skill.py . dist
```

Hasil paket: `dist/pakem.zip` (di-ignore git).

<img src="assets/divider.svg" alt="" width="100%">

<div align="center">

<img src="assets/footer.svg" alt="Terima kasih sudah membaca, petualang. Agent boleh ganti; pakem tetap." width="100%">

</div>

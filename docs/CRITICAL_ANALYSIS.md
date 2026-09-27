# AUTO-PARK — Critical Analysis of the Client's Terms of Reference

This sheet turns the client's brief into explicit requirements, records every
ambiguity found in it and how we resolved it, and shows which module was
proposed to satisfy which requirement. It is the reasoning that sits **before**
the design: `USE_CASES.md` (use cases) → `DESIGN.md` (a/b/c) →
`ARCHITECTURE.md` (implementation).

---

## 1. The ToR, restated as testable requirements

| # | Requirement taken from the brief | Acceptance test |
| --- | --- | --- |
| **R1** | Drivers see a **visual display of available slots before entry** | Anonymous `GET /display/` renders counters + slot map and refreshes itself; no login |
| **R2** | The system **records vehicles on arrival** | POST `/parking/entry/` creates a session with `entry_time`, allocated slot and attendant |
| **R3** | On exit the system **automatically calculates total time spent** | Session stores `duration_minutes`; shown on the exit screen before payment |
| **R4** | On exit it **automatically calculates the amount to pay** | Fee service returns the bracket fee from the brief's table |
| **R5** | **The barrier opens on payment** of the parking fees | Barrier `open` command is issued only after the payment transaction commits |
| **R6** | Charge table: ≤30 min free · ≤2 h KES 50 · ≤4 h KES 100 · ≤6 h KES 300 · >6 h KES 500 | All five brackets *and* every boundary minute asserted in `tests/test_fee_service.py` |
| **R7** | **Web-based**, well-commented system in C++/Java/Python, given an appropriate name | Django + Flask in Python, docstrings/comments throughout, "AUTO-PARK" |
| **R8** | (a) algorithm per module · (b) data structures + reasons · (c) dynamic database | `DESIGN.md` parts (a), (b), (c) |

---

## 2. Critical reading — where the brief is ambiguous

A ToR written this tightly leaves several decisions to the supplier. Each one
below was taken deliberately, is implemented that way, and is reversible.

**A1 — Are the brackets flat or cumulative?** "up to 2 hours Kshs 50; up to 4
hours Kshs 100" does not say whether a 3-hour stay pays 100 (flat) or
50 + 100 = 150 (cumulative). The phrase *"amount to pay"* implies one charge,
so we read them as **flat, first-match-wins bracket fees**. Implemented as an
ordered list scanned in order — if the client later wants cumulative pricing,
only `FEE_BRACKETS` changes, not the algorithm.

**A2 — Are the boundaries inclusive?** "up to 2 hours" is read as
**≤ 120 minutes inclusive**; 121 minutes starts the next bracket. A driver who
leaves at exactly 2:00 pays 50, at 2:01 pays 100. Boundary minutes are the
part users dispute, so each is asserted in the tests.

**A3 — How is a partial minute treated?** Duration is **floored** to whole
minutes (1 h 59 m 59 s = 119 min). Flooring always favours the driver and
never charges for time not spent; ceiling would bill 120 minutes for a stay
that was not 2 hours.

**A4 — Do vehicle types pay differently?** The brief gives **one tariff for
every vehicle**, so a truck pays what a motorcycle pays. `vehicle_type` is
still captured (it is needed for reports and for a future tariff matrix), and
`FEE_BRACKETS` is a single editable literal ready to become
`{vehicle_type: [(bound, fee)]}` without touching the algorithm.

**A5 — "Visual display" = which screen?** Read as a **gate-mounted browser
page**: full-screen, no login, LED-friendly type, 10 s auto-refresh, counters
plus a colour-coded map of every bay (`/display/`). It is deliberately the
only unauthenticated page in the system.

**A6 — Is the barrier real hardware?** No hardware was supplied, so the
barrier is a **separate Flask service with a REST contract**
(`POST /api/barrier/open|close|status`). Swapping in a real controller means
re-pointing one URL; nothing in Django knows about motors, so the ordering
guarantee (open *after* payment) is preserved either way.

**A7 — Failure ordering: what if a service dies mid-exit?** The brief implies
"no payment → no exit". We fail **closed**: the fee is computed *before* any
write (service down ⇒ clean abort, nothing committed), payment + exit + slot
release commit as **one transaction**, and the barrier command is sent only
after commit. A hardware failure after commit degrades to a warning — data is
never wrong because a motor was.

**A8 — Concurrency.** Two attendants can post the same exit, or two arrivals
can race for the last bay. Slot allocation takes the row with
`SELECT … FOR UPDATE` and the exit re-checks `status = ACTIVE` under the same
lock, so double-payment and double-allocation are structurally impossible.

**A9 — Kenya-specific expectations the brief assumes but does not state.**
M-Pesa is a first-class payment method (alongside cash and card); all times
are `Africa/Nairobi`; currency is KES throughout; a live-fee dependency must
survive a flaky network, so the fee call has a 5 s timeout and refuses to
write rather than guessing.

**A10 — Data protection.** Number plates are personal data under the Kenya
Data Protection Act, 2019 when linked to an owner. We store only the plate,
hash every password (PBKDF2), restrict screens by role, and keep history
append-only (`ON DELETE PROTECT`), so records cannot be quietly edited or
orphaned. Retention/deletion policy is a client decision we flag but do not
invent.

---

## 3. Proposed modules (requirement → module)

The ToR decomposes into **ten modules**; nothing in the brief falls outside
them.

| Module | Requirement(s) it closes | Use case |
| --- | --- | --- |
| 1 — Authentication & RBAC | R7 (a system staffed by attendants/admins must be access-controlled) | UC-09, UC-10 |
| 2 — Slot management | R1 (there must be slots to display) | UC-01, UC-06 |
| 3 — Vehicle entry | **R2** | UC-02 |
| 4 — Vehicle exit | **R3** | UC-03, UC-05 |
| 5 — Fee calculation | **R4, R6** | UC-04 |
| 6 — Payment management | **R5** | UC-05 |
| 7 — Barrier control | **R5** | UC-02, UC-05 |
| 8 — Dashboard | management oversight implied by "automate their operations" | UC-07 |
| 9 — Reports | revenue accountability implied by "management would like…" | UC-08 |
| 10 — Public availability display | **R1** | UC-01 |

---

## 4. Honest limitations (what we did *not* claim)

- The barrier and payment capture are **simulations** — the contracts are real,
  the hardware and M-Pesa STK push are not wired up (`payment_status` already
  has `PENDING`/`FAILED` for that callback).
- Single site, single currency, single tariff. Multi-branch pricing, season
  tickets, reservations and ANPR are out of scope of this brief.
- The web UI assumes a gate attendant types the plate; there is no camera.
- No printed receipt (no printer in the ToR); the exit screen confirmation is
  the receipt.

---

## 5. Verdict against the brief

Every clause in the ToR maps to a module, a use case, an algorithm in
`DESIGN.md`, code, and at least one test. The fee table is implemented exactly
as written; the display, arrival record, automatic duration/fee and
pay-then-open barrier were each demonstrated end to end
(`README.md → Testing`). The judgement calls the brief forced (A1–A10) are
documented here so the client can overrule any of them in one place.

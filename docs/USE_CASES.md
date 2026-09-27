# AUTO-PARK – Use Cases

Actors, use cases and the module / code / test each one maps to. This is the
traceability sheet for the brief: *"Using the identified Use Cases, modules,
algorithms and databases develop a functional Modern Parking System."*
The ToR itself — requirements, ambiguities and the decisions taken →
`CRITICAL_ANALYSIS.md`.

## Actors

| Actor | Description | Login |
| --- | --- | --- |
| **Driver** | Arrives at the gate; reads the public availability display *before* entering. Never touches the system. | none |
| **Attendant** | Gate staff: records entries, searches vehicles on exit, takes payment. | `ATTENDANT` |
| **Admin** | Management: slots, reports, users, Django admin. | `ADMIN` / superuser |
| **System** | The software itself – fee engine, barrier control, statistics. | n/a |
| **Flask services** | Fee (`:5000`) and barrier (`:5001`) microservices called by the System. | n/a |

## Use case catalogue

### UC-01 – View parking availability before entry
- **Actor:** Driver
- **Trigger:** Driver approaches the gate and looks at the LED screen.
- **Main flow:** Open `/display/` → see total / occupied / available counters and the slot map (green = free, dark = occupied) → decide to enter.
- **Non-functional:** no login, page auto-refreshes every 10 s, large LED-friendly type.
- **Module:** 10 – Public availability display
- **Code:** `dashboard/views.py: display()` → `templates/dashboard/display.html`
- **Tests:** `tests/test_display.py::DisplayAccessTests` (anonymous 200, no login wall, slot map rendered)

### UC-02 – Record vehicle entry
- **Actor:** Attendant
- **Trigger:** Vehicle arrives at the entry barrier.
- **Main flow:** `/parking/entry/` → type plate + vehicle type → system normalises the plate, rejects a vehicle that is already parked, allocates the next available slot (`SELECT … FOR UPDATE`), creates the session with `entry_time = now` → barrier OPEN command sent to the Flask service → confirmation shown.
- **Alternative flows:**
  - Lot full → `ParkingLotFullError`, nothing written, message shown.
  - Plate already in an active session → `VehicleAlreadyParkedError`.
  - Barrier service down → entry still recorded, amber warning shown.
- **Module:** 3 – Vehicle entry (uses 2 slot management, 7 barrier control)
- **Code:** `parking/views.py: vehicle_entry()` → `services/entry.py: register_entry()` → `services/allocation.py: allocate_slot()` → `services/clients.py: open_gate()`
- **Tests:** `tests/test_flows.py::VehicleEntryServiceTests`, `tests/test_parking.py::SlotAllocationTests`

### UC-03 – Search vehicle and preview the fee on exit
- **Actor:** Attendant
- **Trigger:** Vehicle presents itself at the exit barrier.
- **Main flow:** `/parking/exit/?plate=KDA 123X` → system finds the ACTIVE session → calls the fee service with `entry_time` + `now` → displays time spent and amount payable *before* any payment.
- **Alternative flow:** fee service down → quote suppressed with an explicit "exit cannot be processed" message; nothing is charged.
- **Module:** 4 – Vehicle exit / 5 – Fee calculation
- **Code:** `parking/views.py: vehicle_exit()` (GET) → `services/exit.py: get_active_session()`, `quote_fee()` → `services/clients.py: calculate_fee()` → Flask `POST /api/calculate-fee`
- **Tests:** `tests/test_flows.py::VehicleExitServiceTests`, `tests/test_flows.py::DjangoToFlaskIntegrationTests`

### UC-04 – Calculate the parking fee automatically
- **Actor:** System (via the Flask fee service)
- **Trigger:** UC-03 preview, or UC-05 payment submission.
- **Main flow:** duration in whole minutes → first matching bracket wins → fee returned as JSON.
- **Charge table:** ≤30 min → 0 · ≤2 h → 50 · ≤4 h → 100 · ≤6 h → 300 · >6 h → 500 (KES).
- **Module:** 5 – Fee calculation
- **Code:** `flask_services/fee_service/app.py: FEE_BRACKETS, calculate_fee()` (algorithm documented in `ARCHITECTURE.md → Algorithms`)
- **Tests:** `tests/test_fee_service.py::CalculateFeeTests` (all five brackets *and* the boundary minute of each), `::FeeEndpointTests` (HTTP contract)

### UC-05 – Pay parking fees and exit (barrier opens)
- **Actor:** Attendant + System
- **Trigger:** Driver pays at the exit.
- **Main flow:** submit payment method (CASH / M-PESA / CARD) → one atomic transaction: re-check session still ACTIVE → compute duration + fee → insert `Payment(status=PAID)` → stamp `exit_time`, `duration_minutes`, `amount_paid`, set session COMPLETED → release the slot → commit → **only then** command the barrier OPEN.
- **Key rule:** the barrier is opened *on payment*. If the fee service is down, **no payment and no barrier** (fail closed); if payment fails, the transaction rolls back and the barrier is never commanded.
- **Module:** 4 + 6 – Vehicle exit / Payment management, 7 – Barrier control
- **Code:** `parking/views.py: vehicle_exit()` (POST) → `services/exit.py: register_exit()` → `services/clients.py: open_gate()`
- **Tests:** `tests/test_flows.py::VehicleExitServiceTests`, `::VehicleFlowEndToEndTests` (live services: entry → exit → payment → barrier)

### UC-06 – Manage parking slots
- **Actor:** Admin
- **Trigger:** Capacity change, maintenance, blocked bay.
- **Main flow:** `/parking/` → create slot → set status AVAILABLE / RESERVED / OUT_OF_SERVICE → live counts recompute; occupied slots cannot be silently overwritten (service raises).
- **Module:** 2 – Slot management
- **Code:** `parking/views.py: slot_list, slot_create, slot_update_status()`
- **Tests:** `tests/test_parking.py::SlotAllocationTests`, `::OccupancySummaryTests`

### UC-07 – Monitor live operations
- **Actor:** Admin or Attendant
- **Trigger:** Daily operation.
- **Main flow:** `/` → six statistic cards (slots, occupied, available, vehicles today, revenue today/month) + 7-day entries/exits/revenue trend chart.
- **Module:** 8 – Dashboard
- **Code:** `dashboard/views.py: home()` → `services.py: dashboard_statistics(), trend_series()`
- **Tests:** `tests/test_reports.py::ReportAccessTests::test_dashboard_offers_trend_payload`

### UC-08 – Generate reports and export the session ledger
- **Actor:** Admin (attendant gets 403, anonymous is sent to login)
- **Trigger:** Management wants revenue / occupancy figures.
- **Main flow:** `/reports/` → KPIs, 14-day revenue chart, revenue by payment method, occupancy breakdown, recent sessions → `/reports/export/` downloads the full ledger as CSV (Excel-friendly UTF-8 BOM).
- **Module:** 9 – Reports
- **Code:** `reports/views.py: report_index(), export_sessions()` → `services.py`
- **Tests:** `tests/test_reports.py::ReportAccessTests`, `::ReportFiguresTests`, `::SessionExportTests`

### UC-09 – Sign in under role-based access control
- **Actor:** Attendant, Admin
- **Trigger:** Any restricted page.
- **Main flow:** `/accounts/login/` → session cookie issued (PBKDF2-hashed password) → decorators route by role: signed-in wrong role → **403** "your role does not permit this action"; anonymous → login redirect; password reset emails print to the console in development.
- **Module:** 1 – Authentication
- **Code:** `accounts/decorators.py: _role_gate(), admin_required, attendant_required, role_required, allow_roles`
- **Tests:** `tests/test_parking.py::UserRoleTests`, `tests/test_reports.py::ReportAccessTests`

### UC-10 – Administer raw records
- **Actor:** Admin (superuser)
- **Trigger:** Data correction, user management.
- **Main flow:** `/admin/` → add/change/delete users, slots, vehicles, sessions, payments with the generated ModelAdmins (list displays, filters, fieldsets).
- **Module:** 1 + 2 + 6 (Django admin layer)
- **Code:** `accounts/admin.py`, `parking/admin.py`, `payments/admin.py`
- **Tests:** covered indirectly by superuser fixtures; verified manually against Supabase

## Traceability summary

| Use case | Module(s) | Entry point | Primary tests |
| --- | --- | --- | --- |
| UC-01 View availability | 10 | `/display/` | `test_display.py` |
| UC-02 Record entry | 3, 2, 7 | `/parking/entry/` | `VehicleEntryServiceTests`, `SlotAllocationTests` |
| UC-03 Search + quote | 4, 5 | `/parking/exit/?plate=` | `VehicleExitServiceTests`, `DjangoToFlaskIntegrationTests` |
| UC-04 Fee calculation | 5 | Flask `POST /api/calculate-fee` | `CalculateFeeTests`, `FeeEndpointTests` |
| UC-05 Pay → barrier open | 4, 6, 7 | `/parking/exit/` POST | `VehicleFlowEndToEndTests` |
| UC-06 Manage slots | 2 | `/parking/` | `SlotAllocationTests`, `OccupancySummaryTests` |
| UC-07 Monitor dashboard | 8 | `/` | `ReportAccessTests` |
| UC-08 Reports + export | 9 | `/reports/` | `ReportFiguresTests`, `SessionExportTests` |
| UC-09 Login + RBAC | 1 | `/accounts/login/` | `UserRoleTests`, `ReportAccessTests` |
| UC-10 Django admin | 1, 2, 6 | `/admin/` | admin smoke (superuser) |

Algorithms behind UC-02/03/04/05 → `ARCHITECTURE.md → Algorithms`.
Database tables → `ARCHITECTURE.md → Database schema (Supabase)`.

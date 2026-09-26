"""Unit tests: parking fee calculation (Module 5 - Flask fee service)."""

import importlib.util
import unittest
from datetime import datetime
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "flask_services"
    / "fee_service"
    / "app.py"
)
_spec = importlib.util.spec_from_file_location("fee_service_app", MODULE_PATH)
fee_service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fee_service)


class CalculateFeeTests(unittest.TestCase):
    """Each parking charge bracket from the spec, plus the boundaries."""

    def test_spec_example_180_minutes_is_100(self):
        entry = datetime(2026, 6, 21, 10, 0, 0)
        exit_ = datetime(2026, 6, 21, 13, 0, 0)
        self.assertEqual(
            fee_service.price_session(entry, exit_),
            {"duration_minutes": 180, "fee": 100},
        )

    def test_up_to_30_minutes_is_free(self):
        self.assertEqual(int(fee_service.calculate_fee(0)), 0)
        self.assertEqual(int(fee_service.calculate_fee(30)), 0)

    def test_31_minutes_charges_50(self):
        self.assertEqual(int(fee_service.calculate_fee(31)), 50)

    def test_up_to_2_hours_is_50(self):
        self.assertEqual(int(fee_service.calculate_fee(120)), 50)

    def test_2_hours_1_minute_is_100(self):
        self.assertEqual(int(fee_service.calculate_fee(121)), 100)

    def test_up_to_4_hours_is_100(self):
        self.assertEqual(int(fee_service.calculate_fee(240)), 100)

    def test_up_to_6_hours_is_300(self):
        self.assertEqual(int(fee_service.calculate_fee(360)), 300)

    def test_above_6_hours_is_500(self):
        self.assertEqual(int(fee_service.calculate_fee(361)), 500)
        self.assertEqual(int(fee_service.calculate_fee(480)), 500)

    def test_negative_duration_rejected(self):
        with self.assertRaises(ValueError):
            fee_service.calculate_fee(-1)

    def test_exit_before_entry_rejected(self):
        with self.assertRaises(ValueError):
            fee_service.calculate_duration_minutes(
                datetime(2026, 6, 21, 13, 0), datetime(2026, 6, 21, 10, 0)
            )


class FeeEndpointTests(unittest.TestCase):
    """HTTP contract of POST /api/calculate-fee."""

    def setUp(self):
        self.client = fee_service.app.test_client()

    def test_valid_request_returns_duration_and_fee(self):
        response = self.client.post(
            "/api/calculate-fee",
            json={
                "entry_time": "2026-06-21T10:00:00",
                "exit_time": "2026-06-21T13:00:00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"duration_minutes": 180, "fee": 100})

    def test_missing_fields_return_400(self):
        response = self.client.post("/api/calculate-fee", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_bad_timestamp_returns_400(self):
        response = self.client.post(
            "/api/calculate-fee",
            json={"entry_time": "not-a-date", "exit_time": "2026-06-21T13:00:00"},
        )
        self.assertEqual(response.status_code, 400)

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")


class BarrierServiceTests(unittest.TestCase):
    """Unit tests: barrier control simulation (Module 7)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        barrier_path = (
            Path(__file__).resolve().parent.parent
            / "flask_services"
            / "barrier_service"
            / "app.py"
        )
        spec = importlib.util.spec_from_file_location("barrier_service_app", barrier_path)
        cls.barrier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.barrier)

    def test_open_then_status_reports_open(self):
        result = self.barrier.open_barrier()
        self.assertEqual(result, {"status": "success", "barrier": "opened"})
        self.assertEqual(self.barrier._barrier_state, "open")

    def test_close_returns_closed(self):
        self.barrier.open_barrier()
        result = self.barrier.close_barrier()
        self.assertEqual(result, {"status": "success", "barrier": "closed"})

    def test_open_endpoint_response_shape(self):
        client = self.barrier.app.test_client()
        response = client.post("/api/barrier/open")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(), {"status": "success", "barrier": "opened"}
        )


if __name__ == "__main__":
    unittest.main()

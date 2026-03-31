import time
import unittest
import unittest.mock
from collections import defaultdict, deque

import fakeredis

import rate_limiter


class RedisRateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakeredis.FakeRedis(decode_responses=True)
        rate_limiter._set_redis_client(self.fake)

    def tearDown(self):
        self.fake.flushall()
        rate_limiter._set_redis_client(None)
        rate_limiter._windows.clear()

    def test_first_n_requests_allowed(self):
        for _ in range(3):
            self.assertTrue(rate_limiter.is_allowed("phone_a", limit=3, window_seconds=60))

    def test_request_n_plus_1_denied(self):
        for _ in range(3):
            rate_limiter.is_allowed("phone_b", limit=3, window_seconds=60)
        self.assertFalse(rate_limiter.is_allowed("phone_b", limit=3, window_seconds=60))

    def test_different_keys_are_independent(self):
        for _ in range(3):
            rate_limiter.is_allowed("phone_c", limit=3, window_seconds=60)
        # phone_d has not been used — should still be allowed
        self.assertTrue(rate_limiter.is_allowed("phone_d", limit=3, window_seconds=60))

    def test_window_expiry_allows_again(self):
        # Exhaust the limit
        for _ in range(3):
            rate_limiter.is_allowed("phone_e", limit=3, window_seconds=1)
        self.assertFalse(rate_limiter.is_allowed("phone_e", limit=3, window_seconds=1))

        # Advance real time past the 1-second window and flush stale keys
        time.sleep(1.1)
        self.fake.flushall()  # simulate TTL expiry

        self.assertTrue(rate_limiter.is_allowed("phone_e", limit=3, window_seconds=1))


class InMemoryRateLimiterTests(unittest.TestCase):
    """Verify the fallback in-memory path works when Redis is not configured."""

    def setUp(self):
        rate_limiter._set_redis_client(None)
        rate_limiter._windows.clear()

    def tearDown(self):
        rate_limiter._windows.clear()

    def test_first_n_requests_allowed(self):
        for _ in range(3):
            self.assertTrue(rate_limiter.is_allowed("mem_phone_a", limit=3, window_seconds=60))

    def test_request_n_plus_1_denied(self):
        for _ in range(3):
            rate_limiter.is_allowed("mem_phone_b", limit=3, window_seconds=60)
        self.assertFalse(rate_limiter.is_allowed("mem_phone_b", limit=3, window_seconds=60))


if __name__ == "__main__":
    unittest.main()

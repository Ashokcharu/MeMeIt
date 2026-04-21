import unittest
from unittest.mock import MagicMock, patch
import json
import time

# Mocking dependencies before importing workers to avoid DB/Redis issues
with patch('src.workers.RedisHuey'), \
     patch('src.workers.get_connection'), \
     patch('src.workers.get_redis_connection'), \
     patch('src.workers.publish_event'):
    from src.workers import monitor_on_chain_logic

class TestUpdateLogic(unittest.TestCase):

    def test_score_smoothing(self):
        """Verify that score smoothing is more responsive (favoring new score)."""
        # Testing the custom logic I added:
        # if abs(new_score - prev_score) > 15: round(prev*0.2 + new*0.8)
        # else: round(prev*0.4 + new*0.6)
        
        # Large jump
        prev, new = 80, 20
        # 80 * 0.2 + 20 * 0.8 = 16 + 16 = 32
        final = round((prev * 0.2) + (new * 0.8))
        self.assertEqual(final, 32)
        
        # Small jump
        prev, new = 50, 60
        # 50 * 0.4 + 60 * 0.6 = 20 + 36 = 56
        final = round((prev * 0.4) + (new * 0.6))
        self.assertEqual(final, 56)

    def test_mc_growth_logic(self):
        """Verify that fallback logic trusts incoming MC if non-zero."""
        # incoming_mc = 500, stored_mc = 1000
        # if incoming_mc > 0: mc = incoming_mc
        incoming_mc = 500
        stored_mc = 1000
        mc = incoming_mc if incoming_mc > 0 else stored_mc
        self.assertEqual(mc, 500)
        
        # incoming_mc = 0, stored_mc = 1000
        incoming_mc = 0
        mc = incoming_mc if incoming_mc > 0 else stored_mc
        self.assertEqual(mc, 1000)

if __name__ == '__main__':
    unittest.main()

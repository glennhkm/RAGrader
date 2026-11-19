"""Static guards for Docker Compose settings that broke real deployments."""

import unittest
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _compose(name):
    return yaml.safe_load((BACKEND_DIR / name).read_text(encoding="utf-8"))


class ComposeConfigTest(unittest.TestCase):
    def test_redis_runs_as_redis_user_without_extra_capabilities(self):
        # As root with cap_drop: ALL the official entrypoint cannot read an
        # existing appendonlydir and crash-loops on every restart.
        redis = _compose("docker-compose.yml")["services"]["redis"]
        self.assertEqual("999:1000", str(redis.get("user")))
        self.assertEqual(["ALL"], redis.get("cap_drop"))
        self.assertNotIn("cap_add", redis)

    def test_dev_stack_uses_a_named_data_volume(self):
        # A ./data bind mount is owned by the host user, so the container user
        # (uid 10001) could not create the Chroma database on Linux.
        dev = _compose("docker-compose.dev.yml")
        volumes = dev["services"]["api"]["volumes"]
        self.assertIn("api_data:/app/data", volumes)
        self.assertIn("api_data", dev["volumes"])
        self.assertNotIn("local", dev["services"]["api"].get("profiles", []))
        self.assertEqual(["local"], dev["services"]["ollama"]["profiles"])


if __name__ == "__main__":
    unittest.main()

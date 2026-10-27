"""Compatibility entry point. New code lives in hardware_claw/agent.py."""
from hardware_claw.agent import main

if __name__ == "__main__":
    raise SystemExit(main())

"""兼容入口：python agent.py → 转调 agent.main。"""

from agent.main import main

if __name__ == "__main__":
    main()

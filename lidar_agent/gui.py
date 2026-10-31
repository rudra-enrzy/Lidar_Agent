"""The old desktop window is replaced by the browser app (python -m lidar_agent.app), which shows Potree live.
Kept so that run_gui.bat still works: it simply starts the app."""
from .app import main

if __name__ == "__main__":
    main()

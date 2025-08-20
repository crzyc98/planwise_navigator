# filename: streamlit_dashboard/launch_compensation_tuning.py
"""
Simple launcher script for the compensation tuning interface.
Run this script to start the Streamlit app for E012 compensation tuning.
"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    """Launch the compensation tuning Streamlit interface"""
    print("🚀 Launching PlanWise Navigator Compensation Tuning Interface...")

    # Change to the correct directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    # Check if we're in the right environment
    if not Path("compensation_tuning.py").exists():
        print("❌ Error: compensation_tuning.py not found in current directory")
        return

    # Launch Streamlit
    try:
        print("📊 Starting Streamlit server...")
        print("🌐 The interface will open in your browser at http://localhost:8501")
        print("💡 Use Ctrl+C to stop the server")
        print("=" * 60)

        subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "compensation_tuning.py",
                "--server.port",
                "8501",
                "--server.address",
                "localhost",
            ]
        )

    except KeyboardInterrupt:
        print("\n👋 Shutting down Streamlit server...")
    except Exception as e:
        print(f"❌ Error launching Streamlit: {e}")


if __name__ == "__main__":
    main()

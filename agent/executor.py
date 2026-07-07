import subprocess
import os
import tempfile
import textwrap

class PythonExecutor:
    """Executes Python code in a subprocess safely."""
    
    def __init__(self, output_dir: str, timeout: int = 30):
        self.output_dir = output_dir
        self.timeout = timeout
        os.makedirs(self.output_dir, exist_ok=True)
        
    def execute(self, code: str) -> dict:
        """
        Executes the provided python code. 
        Pre-imports pandas and matplotlib, and sets the working directory.
        """
        # Wrap the code to ensure charts are saved instead of shown interactively
        wrapped_code = textwrap.dedent(f"""
        import pandas as pd
        import matplotlib.pyplot as plt
        import os
        
        # Set output dir
        OUTPUT_DIR = '{self.output_dir}'
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Override plt.show to save instead (simple mock)
        def save_plot(*args, **kwargs):
            plt.savefig(os.path.join(OUTPUT_DIR, 'plot.png'))
            print("Plot saved to", os.path.join(OUTPUT_DIR, 'plot.png'))
        plt.show = save_plot

        """) + "\n" + code

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(wrapped_code)
            temp_script = f.name
            
        try:
            result = subprocess.run(
                ["python", temp_script],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired as e:
            return {
                "stdout": e.stdout.decode('utf-8') if e.stdout else "",
                "stderr": f"Execution timed out after {self.timeout} seconds.",
                "exit_code": 124
            }
        finally:
            if os.path.exists(temp_script):
                os.remove(temp_script)

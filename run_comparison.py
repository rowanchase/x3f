import subprocess
import os

files = [
    "_P2M0993.X3F", # Best
    "_P2M0936.X3F", # Worst (Clipped)
    "_P2M1003.X3F"  # ISO 400
]

base_cmd = ["python3", "tools/compare_output.py"]
extract_path = "./bin/linux-x86_64/x3f_extract"

for f in files:
    x3f = os.path.join("reference_files/X3Fs", f)
    tiff = os.path.join("reference_files/TIFFs", f.replace(".X3F", ".tif"))
    
    cmd = base_cmd + [x3f, tiff, "--x3f-extract", extract_path]
    print(f"Running for {f}...")
    subprocess.run(cmd)
    print("-" * 50)

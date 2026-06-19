import json

commands = [
    "cd /home/ubuntu/loadtest && python3 parse_results.py results/20260618T171826Z 2>&1 | tail -60",
]

with open(r"C:\Users\user\AppData\Local\Temp\parse_params.json", "w") as f:
    json.dump({"commands": commands}, f)
print("ok")

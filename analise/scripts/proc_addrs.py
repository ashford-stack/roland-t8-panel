import json
import re

d = json.load(open("/tmp/proc.json"))
s = json.dumps(d)
addrs = sorted(set(re.findall(r"0[xX]0*80[0-9a-fA-F]+", s)), key=lambda x: int(x, 16))
print("\n".join(addrs))

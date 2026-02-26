"""Parse Copilot Studio dialog.json trace file."""
import json
import sys

path = r"C:\Users\graham\Desktop\dialog.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

acts = data.get("activities", [])
print(f"Total activities: {len(acts)}\n")

# Summary of NON-typing activities only
print("=== ACTIVITY SUMMARY (non-typing) ===")
for i, a in enumerate(acts):
    atype = a.get("type", "?")
    if atype == "typing":
        continue
    role = a.get("from", {}).get("role", "?")
    name = a.get("name", "")
    text = str(a.get("text", ""))[:120].replace("\n", " ")
    label = a.get("label", "")
    vtype = a.get("valueType", "")
    extra = ""
    if name:
        extra += f" name={name}"
    if label:
        extra += f" label={label}"
    if vtype:
        extra += f" valueType={vtype}"
    print(f"[{i:3d}] type={atype:20s} role={role:6s}{extra} text={text}")

# User messages
print("\n=== USER MESSAGES ===")
for i, a in enumerate(acts):
    if a.get("type") == "message" and a.get("from", {}).get("role") == "user":
        text = str(a.get("text", ""))
        print(f"\n--- Activity [{i}] ---")
        print(text[:500])

# DynamicPlanStepFinished observations (full detail)
print("\n=== PLAN STEP FINISHED - OBSERVATIONS ===")
for i, a in enumerate(acts):
    name = a.get("name", "")
    if name == "DynamicPlanStepFinished":
        value = a.get("value", {})
        obs = value.get("observation", {})
        obs_str = json.dumps(obs, indent=2) if isinstance(obs, dict) else str(obs)
        print(f"\n--- Activity [{i}] ---")
        print(f"observation ({len(obs_str)} chars):")
        print(obs_str[:3000])

# Check for duplicate text in bot messages
print("\n=== DUPLICATE TEXT CHECK ===")
for i, a in enumerate(acts):
    if a.get("type") == "message" and a.get("from", {}).get("role") == "bot":
        text = str(a.get("text", ""))
        if len(text) > 100:
            half = len(text) // 2
            first_half = text[:half]
            second_half = text[half:]
            # Check if the second half starts similarly to the first half
            # Find the longest common prefix
            overlap = 0
            for j in range(min(100, len(first_half), len(second_half))):
                if first_half[j] == second_half[j]:
                    overlap += 1
                else:
                    break
            if overlap > 20:
                print(f"  Activity [{i}]: LIKELY DUPLICATE - first {overlap} chars of each half match")
                print(f"    Text length: {len(text)}")
                print(f"    First half starts: {first_half[:100]}")
                print(f"    Second half starts: {second_half[:100]}")
            else:
                # Also check if text contains itself
                mid = len(text) // 2
                needle = text[:min(80, mid)]
                second_occurrence = text.find(needle, len(needle))
                if second_occurrence > 0:
                    print(f"  Activity [{i}]: TEXT REPEATS at position {second_occurrence}")
                    print(f"    Text length: {len(text)}")
                    unique_part = text[:second_occurrence]
                    print(f"    Unique part ({len(unique_part)} chars): {unique_part[:200]}")
                    print(f"    Repeated part starts: {text[second_occurrence:second_occurrence+200]}")

# Skip earlier sections already analyzed
# Jump to focused analysis

# A2A Protocol Trace Data
print("=== A2A PROTOCOL TRACE DATA ===")
for i, a in enumerate(acts):
    name = a.get("name", "")
    if name == "Agent2AgentProtocolTraceData":
        value = a.get("value", {})
        print(f"\n--- Activity [{i}] ---")
        print(f"  value keys: {list(value.keys())}")
        for k, v in value.items():
            v_str = json.dumps(v, indent=2) if isinstance(v, (dict, list)) else str(v)
            if len(v_str) > 3000:
                print(f"  {k} ({len(v_str)} chars): {v_str[:3000]}...")
            else:
                print(f"  {k}: {v_str}")

# DynamicPlanStepBindUpdate - shows how orchestrator binds the observation
print("\n=== PLAN STEP BIND UPDATES ===")
for i, a in enumerate(acts):
    name = a.get("name", "")
    if name == "DynamicPlanStepBindUpdate":
        value = a.get("value", {})
        print(f"\n--- Activity [{i}] ---")
        v_str = json.dumps(value, indent=2) if isinstance(value, dict) else str(value)
        print(v_str[:2000])

# DynamicPlanReceived - shows the plan structure
print("\n=== DYNAMIC PLAN RECEIVED ===")
for i, a in enumerate(acts):
    name = a.get("name", "")
    if name == "DynamicPlanReceived":
        value = a.get("value", {})
        print(f"\n--- Activity [{i}] ---")
        v_str = json.dumps(value, indent=2) if isinstance(value, dict) else str(value)
        print(v_str[:3000])

# End of trace analysis

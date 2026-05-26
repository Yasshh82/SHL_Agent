# chat.py — run with: python chat.py
import requests, json

BASE = "http://localhost:8000"
messages = []

print("SHL Assessment Advisor — type 'quit' to exit\n")

while True:
    user_input = input("You: ").strip()
    if user_input.lower() in {"quit", "exit", "q"}:
        break
    if not user_input:
        continue

    messages.append({"role": "user", "content": user_input})

    try:
        resp = requests.post(f"{BASE}/chat", json={"messages": messages}, timeout=35)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[error] {e}\n")
        messages.pop()  # remove the failed user message
        continue

    reply = data["reply"]
    recs  = data.get("recommendations", [])
    eoc   = data.get("end_of_conversation", False)

    print(f"\nAgent: {reply}")

    if recs:
        print("\n  Recommendations:")
        for i, r in enumerate(recs, 1):
            print(f"  {i}. {r['name']} [{r['test_type']}]")
            print(f"     {r['url']}")

    print()
    messages.append({"role": "assistant", "content": reply})

    if eoc:
        print("Agent has closed the conversation.")
        break
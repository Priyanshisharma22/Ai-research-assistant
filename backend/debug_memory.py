"""
debug_memory.py
---------------
Run this to see exactly what's saved in your SQLite DB.
Place in: C:\\research-assistant\\backend\\
Run with: python debug_memory.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory.long_term import list_sessions, get_session_history
from memory.episodic import get_episodes

print("\n" + "="*60)
print("  LONG-TERM MEMORY DEBUG")
print("="*60)

sessions = list_sessions(limit=20)

if not sessions:
    print("\n❌ NO SESSIONS FOUND IN DATABASE!")
    print("   This means save_message() is never being called.")
    print("   → Check orchestrator.py has the lt_save() calls.")
else:
    print(f"\n✅ Found {len(sessions)} session(s) in database:\n")
    for s in sessions:
        print(f"  session_id    : {s['session_id']}")
        print(f"  message_count : {s['message_count']}")
        print(f"  persona       : {s['persona']}")
        print(f"  updated_at    : {s['updated_at'][:19]}")

        history = get_session_history(s['session_id'], limit=4)
        print(f"  last messages :")
        for m in history[-4:]:
            content_preview = m['content'][:80].replace('\n', ' ')
            print(f"    [{m['role']:9}] {content_preview}")
        print()

print("="*60)
print("\n⚠  If you see sessions BUT the app still forgets you after")
print("   refresh → the frontend is sending a DIFFERENT session_id")
print("   each time. Fix: use utils/session.ts → getSessionId().\n")

print("\n" + "="*60)
print("  EPISODIC MEMORY DEBUG")
print("="*60)

episodes = get_episodes(limit=20)

if not episodes:
    print("\n❌ NO EPISODES FOUND!")
    print("   Episodic memory is empty — nothing memorable has been saved yet.")
else:
    print(f"\n✅ Found {len(episodes)} episode(s):\n")
    for ep in episodes:
        print(f"  [{ep['event_type'].upper():10}] importance={ep['importance']:.1f} | {ep['session_date']}")
        print(f"    {ep['summary'][:100]}")
        if ep['tags']:
            print(f"    tags: {ep['tags']}")
        print()

print("="*60)
print("\n💡 TIP: Episodes with importance < 0.6 are filtered from")
print("   memory context. Raise importance when saving user facts.\n")
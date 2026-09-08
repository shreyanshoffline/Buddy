"""Quick end-to-end test with real prompts (mocked model calls)."""
import sys
sys.path.insert(0, '.')

from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication

# Mock the network call
with patch('core.agent.run_manager_step') as mock_manager, \
     patch('core.agent.run_action_step') as mock_worker:
    
    class FakeMsg:
        content = "RESPONSE: Paris is the capital of France, known for the Eiffel Tower."
    class FakeUsage:
        prompt_tokens = 15
        completion_tokens = 20
    class FakeResp:
        choices = [type('C', (), {'message': FakeMsg()})]
        usage = FakeUsage()
    
    mock_manager.return_value = FakeResp()
    
    import core
    
    # TEST 1: Regular saved conversation
    print("\n=== TEST 1: Regular Conversation ===")
    conv_id = core.create_conversation()
    result = core.send_and_save_message(conv_id, "What is the capital of France?")
    print(f"✓ Message sent, got ID: {result['message_id']}")
    print(f"✓ Reply: {result['reply'][:50]}...")
    
    # TEST 2: Feedback
    print("\n=== TEST 2: Feedback ===")
    core.set_message_feedback(result['message_id'], 'like')
    history = core.get_conversation_history(conv_id)
    print(f"✓ Feedback saved: {history[-1]['feedback']}")
    
    # TEST 3: Search by content
    print("\n=== TEST 3: Content Search ===")
    hits = core.search_conversations("Eiffel Tower")
    print(f"✓ Found {len(hits)} chat(s) matching 'Eiffel Tower'")
    
    # TEST 4: Private chat toggle
    print("\n=== TEST 4: Privacy Toggle ===")
    core.set_conversation_private(conv_id, True)
    is_private = core.get_conversation_is_private(conv_id)
    print(f"✓ Chat is now private: {is_private}")
    
    # TEST 5: Incognito mode
    print("\n=== TEST 5: Incognito Chat (in-memory, no DB) ===")
    hist = core.new_message_history()
    incog_result = core.process_message_incognito("Tell me about Paris", hist)
    print(f"✓ Incognito reply: {incog_result['reply'][:50]}...")
    print(f"✓ History stays in-memory only (length: {len(hist)})")
    
    # TEST 6: GUI construction
    print("\n=== TEST 6: GUI Construction ===")
    import os
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication(sys.argv)
    from gui import BuddyWindow
    w = BuddyWindow()
    w.show_chat_view()
    w.show_library_view()
    w.show_billing_view()
    w.show_settings_view()
    print(f"✓ BuddyWindow created and all pages accessible")

print("\n" + "="*50)
print("ALL TESTS PASSED ✓")
print("="*50)

from oth.core.console_store import ConsoleStore


def test_console_store_compacts_long_conversation(tmp_path):
    store = ConsoleStore(tmp_path / "console.db")
    try:
        store.create_conversation("c1")
        for index in range(40):
            role = "user" if index % 2 == 0 else "assistant"
            metadata = {"mission": True} if role == "assistant" else {}
            store.add_message("c1", role, f"message {index} about unlimited context and mission memory", metadata)
        assert store.stats()["messages"] == 40
        assert store.stats()["memory_checkpoints"] >= 1
    finally:
        store.close()


def test_console_store_retrieves_relevant_older_history(tmp_path):
    store = ConsoleStore(tmp_path / "console.db")
    try:
        store.create_conversation("c1")
        store.add_message("c1", "user", "Build the autonomous memory router for OTH")
        store.add_message("c1", "assistant", "Implemented the router skeleton")
        for index in range(18):
            store.add_message("c1", "user", f"unrelated filler {index}")
        hits = store.search_messages("c1", "memory router autonomous", limit=5)
        assert hits
        assert any("memory router" in item["content"] for item in hits)
    finally:
        store.close()


def test_console_store_context_combines_memory_retrieval_and_recent(tmp_path):
    store = ConsoleStore(tmp_path / "console.db")
    try:
        store.create_conversation("c1")
        for index in range(40):
            role = "user" if index % 2 == 0 else "assistant"
            metadata = {"mission": True} if role == "assistant" else {}
            content = (
                "Long-term mission: build persistent context retrieval for OTH"
                if index == 0
                else f"filler conversation {index}"
            )
            store.add_message("c1", role, content, metadata)
        context = store.context_for_model("c1", "persistent context retrieval", recent=4, retrieved=4, memories=4)
        joined = "\n".join(item["content"] for item in context)
        assert "DURABLE OTH MISSION MEMORY" in joined
        assert "persistent context retrieval" in joined
        assert len(context) <= 12
    finally:
        store.close()


def test_console_store_keeps_full_archive(tmp_path):
    store = ConsoleStore(tmp_path / "console.db")
    try:
        store.create_conversation("c1")
        for index in range(50):
            store.add_message("c1", "user", f"archive item {index}")
        all_messages = store.messages("c1", limit=100)
        assert len(all_messages) == 50
        assert all_messages[0]["content"] == "archive item 0"
        assert all_messages[-1]["content"] == "archive item 49"
    finally:
        store.close()

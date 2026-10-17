"""Provider-boundary tests; the self-hosted path never makes a real request."""

import pytest


def _reset_client_cache(models):
    models._client_cache = {"key": None, "client": None}


def test_self_hosted_chat_uses_openai_compatible_endpoint(monkeypatch):
    import models

    monkeypatch.setenv("BUDDY_AI_PROVIDER", "self_hosted")
    monkeypatch.setenv("BUDDY_SELF_HOSTED_URL", "http://model.test/v1")
    monkeypatch.setenv("BUDDY_SELF_HOSTED_MODEL", "Qwen3-1.7B-Instruct")
    monkeypatch.setenv("BUDDY_SELF_HOSTED_API_KEY", "")
    _reset_client_cache(models)
    calls = []

    class Response:
        ok = True

        def json(self):
            return {
                "id": "chatcmpl-test",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Done."},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            }

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(models.requests, "post", fake_post)
    response = models.run_manager_step(
        "anthropic/claude-haiku-5.5",
        [{"role": "user", "content": "hello"}],
        32,
    )

    assert response.choices[0].message.content == "Done."
    assert calls[0][0] == "http://model.test/v1/chat/completions"
    assert calls[0][1]["json"]["model"] == "Qwen3-1.7B-Instruct"


def test_self_hosted_tool_calls_keep_the_existing_response_shape(monkeypatch):
    import models

    monkeypatch.setenv("BUDDY_AI_PROVIDER", "self_hosted")
    monkeypatch.setenv("BUDDY_SELF_HOSTED_URL", "http://model.test/v1")
    monkeypatch.setenv("BUDDY_SELF_HOSTED_MODEL", "Qwen3-1.7B-Instruct")
    _reset_client_cache(models)

    class Response:
        ok = True

        def json(self):
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "finish_task", "arguments": '{"summary":"Done"}'},
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
            }

    monkeypatch.setattr(models.requests, "post", lambda *args, **kwargs: Response())
    response = models.run_action_step("cloud/model", [], 128, tools=[{"type": "function"}])
    call = response.choices[0].message.tool_calls[0]
    assert call.function.name == "finish_task"
    assert call.function.arguments == '{"summary":"Done"}'


def test_self_hosted_memory_can_use_keyword_fallback(monkeypatch):
    import models

    monkeypatch.setenv("BUDDY_AI_PROVIDER", "self_hosted")
    monkeypatch.setenv("BUDDY_SELF_HOSTED_URL", "http://model.test/v1")
    monkeypatch.delenv("BUDDY_SELF_HOSTED_EMBEDDING_MODEL", raising=False)
    _reset_client_cache(models)
    with pytest.raises(models.ProviderConfigurationError):
        models.embed_texts(["local memory"])

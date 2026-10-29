"""Per-turn cost guard, including repeated input and tool schemas; no API calls."""
import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, convert_to_openai_messages
from langchain_core.utils.function_calling import convert_to_openai_tool


class TokenBudgetLimitExceededError(RuntimeError):
    pass


class TokenBudgetMiddleware(AgentMiddleware):
    """A fresh instance belongs to one execute_turn, never shared between chats.

    UTF-8 bytes plus framing is a deliberately conservative local estimate, not
    the provider's tokenizer or a currency/billing guarantee. Reserve before
    dispatch, reconcile only when the provider reports valid complete usage.
    """

    def __init__(self, total, output):
        self.total = total
        self.output = output
        self.spent = 0

    def prepare(self, request):
        messages = ([request.system_message] if request.system_message else []) + request.messages
        payload = {
            # Count the chat protocol, not local LangChain objects. model_dump
            # duplicates tool_calls in additional_kwargs and includes usage,
            # response metrics and tracing IDs that are never sent as input.
            'messages': convert_to_openai_messages(messages),
            'tools': [convert_to_openai_tool(t) for t in request.tools],
            'tool_choice': request.tool_choice,
        }
        # Never estimate only the latest user text: history and tool results
        # are sent again on every request. Schema and framing are also charged.
        estimate = len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) + 4096
        remaining = self.total - self.spent - estimate
        if remaining < 256:
            raise TokenBudgetLimitExceededError(
                f'本轮token预算上限{self.total:,}；已计入{self.spent:,}，'
                f'下一次输入保守估算{estimate:,}，已在发送API前停止。')
        output = min(self.output, remaining, request.model_settings.get('max_tokens', self.output))
        reserved = estimate + output
        self.spent += reserved  # Exceptions/missing usage never refund a request.
        return request.override(model_settings={**request.model_settings, 'max_tokens': output}), reserved

    def reconcile(self, response, reserved):
        messages = [m for m in response.result if isinstance(m, AIMessage)]
        usages = [m.usage_metadata for m in messages]
        if usages and all(u and all(isinstance(u.get(k), int) and not isinstance(u[k], bool) and u[k] >= 0
                                   for k in ('input_tokens', 'output_tokens', 'total_tokens'))
                          and u['total_tokens'] >= u['input_tokens'] + u['output_tokens'] for u in usages):
            self.spent += sum(u['total_tokens'] for u in usages) - reserved
        return response

    def wrap_model_call(self, request, handler):
        prepared, reserved = self.prepare(request)
        return self.reconcile(handler(prepared), reserved)

    async def awrap_model_call(self, request, handler):
        prepared, reserved = self.prepare(request)
        return self.reconcile(await handler(prepared), reserved)

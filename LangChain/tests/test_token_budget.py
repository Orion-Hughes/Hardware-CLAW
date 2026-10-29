import unittest
from unittest.mock import patch
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from hardware_claw.token_budget import TokenBudgetMiddleware, TokenBudgetLimitExceededError
from test_agent import ScriptedModel


def request(text='hi', tools=None):
    return ModelRequest(model=ScriptedModel(), messages=[HumanMessage(content=text)],
                        system_message=SystemMessage(content='system'), tools=tools or [])


class TokenBudgetTests(unittest.IsolatedAsyncioTestCase):
    def test_local_response_metadata_not_charged_as_input(self):
        call={'name':'lookup','args':{'query':'x'},'id':'t','type':'tool_call'}
        plain=AIMessage(content='',tool_calls=[call])
        rich=plain.model_copy(update={
            'response_metadata': {'local_debug': 'x'*100000},
            'usage_metadata': {'input_tokens':100,'output_tokens':10,'total_tokens':110},
            'additional_kwargs': {'tool_calls':[{'id':'t','type':'function',
                'function':{'name':'lookup','arguments':'{"query":"x"}'}}]},
        })
        reservations=[]
        for msg in (plain,rich):
            req=request().override(messages=[HumanMessage(content='hi'),msg,
                ToolMessage(content='result',tool_call_id='t')])
            _,reserved=TokenBudgetMiddleware(30000,1024).prepare(req)
            reservations.append(reserved)
        self.assertEqual(reservations[0],reservations[1])

    def test_large_tool_arguments_are_still_counted(self):
        msg=AIMessage(content='',tool_calls=[{'name':'write','id':'t',
            'args':{'files':{'main.cpp':'x'*15000}},'type':'tool_call'}])
        req=request().override(messages=[msg,ToolMessage(content='ok',tool_call_id='t')])
        with self.assertRaises(TokenBudgetLimitExceededError):
            TokenBudgetMiddleware(14000,1024).prepare(req)

    async def test_full_agent_stops_before_first_model_call(self):
        from hardware_claw.agent import build_agent
        model = ScriptedModel()
        with patch('hardware_claw.limits.QUERY_TOTAL_TOKENS', 5000):
            with self.assertRaises(TokenBudgetLimitExceededError):
                await build_agent(model).ainvoke({'messages': [('user', 'hello')]})
        self.assertEqual(model._count, 0)

    def test_reject_before_dispatch(self):
        guard = TokenBudgetMiddleware(5000, 1024)
        calls = []
        with self.assertRaises(TokenBudgetLimitExceededError):
            guard.wrap_model_call(request('x' * 6000), lambda r: calls.append(r))
        self.assertEqual(calls, [])

    def test_counts_tool_schema_and_history(self):
        guard = TokenBudgetMiddleware(10000, 1024)
        req = request().override(messages=[HumanMessage(content='hi'), ToolMessage(content='x'*12000, tool_call_id='a')])
        with self.assertRaises(TokenBudgetLimitExceededError):
            guard.prepare(req)
        schema = {'type': 'function', 'function': {'name': 'example', 'description': 'x'*12000,
                                                 'parameters': {'type': 'object', 'properties': {}}}}
        with self.assertRaises(TokenBudgetLimitExceededError):
            guard.prepare(request(tools=[schema]))

    def test_output_capped_and_actual_usage_accumulates(self):
        guard = TokenBudgetMiddleware(16000, 1024)
        def handler(req):
            self.assertLessEqual(req.model_settings['max_tokens'], 1024)
            return ModelResponse(result=[AIMessage(content='ok', usage_metadata={
                'input_tokens': 11000, 'output_tokens': 200, 'total_tokens': 11200})])
        guard.wrap_model_call(request(), handler)
        self.assertEqual(guard.spent, 11200)
        with self.assertRaises(TokenBudgetLimitExceededError):
            guard.prepare(request('x'*2000))

    def test_missing_usage_and_exception_keep_reservation(self):
        guard = TokenBudgetMiddleware(20000, 1024)
        guard.wrap_model_call(request(), lambda r: ModelResponse(result=[AIMessage(content='ok')]))
        first = guard.spent
        self.assertGreater(first, 4096)
        def fail(req):
            raise RuntimeError('network fixture')
        with self.assertRaises(RuntimeError):
            guard.wrap_model_call(request(), fail)
        self.assertGreater(guard.spent, first)
        self.assertEqual(TokenBudgetMiddleware(20000, 1024).spent, 0)

    async def test_async_repeated_calls_stop(self):
        guard = TokenBudgetMiddleware(14000, 1024)
        calls = []
        async def handler(req):
            calls.append(req)
            return ModelResponse(result=[AIMessage(content='ok', usage_metadata={
                'input_tokens': 9000, 'output_tokens': 500, 'total_tokens': 9500})])
        await guard.awrap_model_call(request(), handler)
        with self.assertRaises(TokenBudgetLimitExceededError):
            await guard.awrap_model_call(request('x'*2000), handler)
        self.assertEqual(len(calls), 1)

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from harness.llm_solvers import is_infeasible, _code_answer, agent_solve
from harness.llm import MODEL_REASON
from harness.tasks import Task
from harness.strategies import get
from harness.strategy import TaskView, RunState, AttemptResult, FAILED, ANSWERED_UNVERIFIED


async def direct_call(function, *args, **kwargs):
    """Keep policy tests independent of thread-pool shutdown behavior."""
    return function(*args, **kwargs)


class Policy(unittest.TestCase):
    def test_policy_has_no_blind_retries_votes_or_preflight(self):
        s=get('reason_first_bounded');t=TaskView('math_a','math',5,'exact_int')
        state=RunState(100000,0,98000,0,3300)
        result=AttemptResult('math_a',1,'oneshot',MODEL_REASON,FAILED,None,'none',10,1)
        self.assertFalse(s.should_escalate(t,result,state))
        self.assertFalse(s.should_verify(t,result,state))
        self.assertFalse(s.should_diagnose(t,state))
        self.assertEqual(s.model_for(t,state,1),MODEL_REASON)
        self.assertEqual(s.max_tool_steps,6)
        self.assertFalse(get('always_reason_no_vote').should_verify(t,result,state))
        self.assertTrue(get('always_reason').should_escalate(t,result,state))

    def test_refusal_requires_explicit_marker(self):
        self.assertTrue(is_infeasible('INFEASIBLE'))
        self.assertTrue(is_infeasible('IMPOSSIBLE: contradictory constraints'))
        self.assertFalse(is_infeasible('This is not IMPOSSIBLE'))
        self.assertFalse(is_infeasible('Mission IMPOSSIBLE'))
        self.assertFalse(is_infeasible('```python\nx="INFEASIBLE"\nprint(42)\n```'))

class Repairs(unittest.IsolatedAsyncioTestCase):
    async def test_only_execution_error_causes_one_repair_with_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Task('math_a','math','fixture',1,'exact_int',Path(tmp))
            llm=type('Fake',(),{})();llm.chat=AsyncMock(side_effect=[
                {'content':'```python\nprint(1/0)\n```','cost':10},
                {'content':'```python\nprint(42)\n```','cost':10}])
            with (patch('harness.llm_solvers.sandbox.run_python',side_effect=[(1,'ZeroDivisionError: division by zero'),(0,'42')]),
                  patch('harness.llm_solvers.asyncio.to_thread', new=direct_call)):
                result=await _code_answer(llm,t,'fixture',Path(tmp),MODEL_REASON,350,'math:math_a',repairs=1)
            self.assertEqual(result[:2],('answer','42'))
            self.assertEqual(llm.chat.await_count,2)
            messages=llm.chat.call_args.args[0]
            self.assertIn('ZeroDivisionError',messages[-1]['content'])
            self.assertIn('1/0',messages[-2]['content'])
            self.assertEqual(t.cost,20)

    async def test_timeout_and_success_do_not_trigger_repair(self):
        for outcome in ((124,'TIMEOUT'),(0,'42')):
            with tempfile.TemporaryDirectory() as tmp:
                t=Task('math_a','math','fixture',1,'exact_int',Path(tmp))
                llm=type('Fake',(),{})();llm.chat=AsyncMock(return_value={'content':'```python\nprint(42)\n```','cost':10})
                with (patch('harness.llm_solvers.sandbox.run_python',return_value=outcome),
                      patch('harness.llm_solvers.asyncio.to_thread', new=direct_call)):
                    await _code_answer(llm,t,'fixture',Path(tmp),MODEL_REASON,350,'math:math_a',repairs=1)
                self.assertEqual(llm.chat.await_count,1)

    async def test_repeated_tool_sequence_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Task('other_a','other','fixture',1,'exact_str',Path(tmp))
            llm=type('Fake',(),{})();llm.chat=AsyncMock(return_value={'content':'','cost':1,
                'tool_calls':[{'id':'one','name':'list_files','arguments':'{}'}]})
            with patch('harness.llm_solvers._schemas',return_value=([],{})):
                result=await agent_solve(llm,t,100,model=MODEL_REASON,max_steps=6,stop_repeated=True)
            self.assertEqual(result[0],'error')
            self.assertEqual(llm.chat.await_count,3)

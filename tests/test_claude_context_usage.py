import unittest

from bridge.clients.claude.context import context_fields


def assistant(prompt, cache_create=0, cache_read=0, *, model='claude-fixture', window=None, **extra):
    usage = {'input_tokens': prompt, 'cache_creation_input_tokens': cache_create,
             'cache_read_input_tokens': cache_read, 'output_tokens': 999999}
    if window is not None:
        usage['context_window'] = window
    return {'type': 'assistant', 'message': {'id': 'step', 'model': model, 'usage': usage}, **extra}


class ClaudeContextUsage(unittest.TestCase):
    def test_latest_main_request_includes_cache_but_not_cumulative_or_output(self):
        events = [assistant(10, 20, 30), {'type': 'result', 'usage': {'input_tokens': 999999}},
                  assistant(100, 200, 300, model='claude-current'),
                  assistant(999, 999, 999, isSidechain=True)]
        result = context_fields(events)
        self.assertEqual(result['contextUsage'], {'usedTokens': 600, 'contextWindow': None,
                         'measurement': 'lastPrompt', 'model': 'claude-current', 'compacted': False})
        self.assertEqual(result['contextUsageStatus'], 'available')

    def test_compaction_invalidates_old_reading_until_next_request(self):
        events = [assistant(1500, window=200000), {'type': 'system', 'subtype': 'compact_boundary'}]
        self.assertEqual(context_fields(events), {'contextUsage': None, 'contextUsageStatus': 'unavailable'})
        result = context_fields(events + [assistant(90, 10, 20, window=200000)])
        self.assertEqual(result['contextUsage']['usedTokens'], 120)
        self.assertEqual(result['contextUsage']['contextWindow'], 200000)
        self.assertTrue(result['contextUsage']['compacted'])

    def test_matching_result_model_supplies_capacity_without_using_cumulative_tokens(self):
        result = {'type': 'result', 'usage': {'input_tokens': 999999}, 'modelUsage': {
            'old-model': {'inputTokens': 888888, 'contextWindow': 1000000},
            'new-model': {'inputTokens': 777777, 'contextWindow': 200000}}}
        reading = context_fields([assistant(10, 20, 30, model='old-model'),
                                  assistant(40, 50, 60, model='new-model'), result])['contextUsage']
        self.assertEqual(reading['usedTokens'], 150)
        self.assertEqual(reading['contextWindow'], 200000)
        self.assertEqual(reading['model'], 'new-model')
        self.assertIsNone(context_fields([assistant(1, model='unknown-model'), result])['contextUsage']['contextWindow'])
        self.assertIsNone(context_fields([assistant(1, model='new-model'), result,
                                          assistant(2, model='new-model')])['contextUsage']['contextWindow'])
        self.assertIsNone(context_fields([assistant(1, model='new-model'),
                                          {**result, 'isSyntheticResult': True}])['contextUsage']['contextWindow'])
        self.assertIsNone(context_fields([assistant(1, model='new-model'),
                                          {'type': 'system', 'subtype': 'compact_boundary'}, result])['contextUsage'])

    def test_unknown_and_zero_are_distinct(self):
        self.assertIsNone(context_fields([assistant(None)])['contextUsage'])
        self.assertEqual(context_fields([assistant(0)])['contextUsage']['usedTokens'], 0)
        self.assertIsNone(context_fields([assistant(1, window=-1)])['contextUsage']['contextWindow'])


if __name__ == '__main__':
    unittest.main()

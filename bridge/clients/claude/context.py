"""Context readings from Claude's per-request assistant usage records."""


def _count(value):
    return value if type(value) is int and value >= 0 else None


def context_fields(events):
    reading = None
    compacted = False
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'system' and event.get('subtype') == 'compact_boundary':
            reading = None
            compacted = True
            continue
        if (event.get('type') == 'result' and reading is not None and reading['model']
                and not event.get('isSidechain') and not event.get('parent_tool_use_id')
                and not event.get('isSyntheticResult') and not event.get('isSynthetic')
                and not event.get('isMeta') and not event.get('isCompactSummary')):
            models = event.get('modelUsage')
            details = models.get(reading['model']) if isinstance(models, dict) else None
            capacity = _count(details.get('contextWindow')) if isinstance(details, dict) else None
            if capacity:
                reading['contextWindow'] = capacity
            continue
        if (event.get('type') != 'assistant' or event.get('isSidechain') or
                event.get('parent_tool_use_id') or event.get('isSynthetic') or
                event.get('isMeta') or event.get('isCompactSummary')):
            continue
        message = event.get('message')
        if not isinstance(message, dict) or not isinstance(message.get('usage'), dict):
            continue
        usage = message['usage']
        input_tokens = _count(usage.get('input_tokens'))
        if input_tokens is None:
            continue
        cache_create = _count(usage.get('cache_creation_input_tokens')) or 0
        cache_read = _count(usage.get('cache_read_input_tokens')) or 0
        model = message.get('model') if isinstance(message.get('model'), str) else ''
        # A capacity from the native request is usable; a model-name guess is not.
        capacity = _count(usage.get('context_window')) or _count(message.get('context_window'))
        reading = {'usedTokens': input_tokens + cache_create + cache_read,
                   'contextWindow': capacity if capacity and capacity > 0 else None,
                   'measurement': 'lastPrompt', 'model': model, 'compacted': compacted}
    return {'contextUsage': reading,
            'contextUsageStatus': 'available' if reading is not None else 'unavailable'}

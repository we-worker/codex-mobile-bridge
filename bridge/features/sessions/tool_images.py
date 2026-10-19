"""Extract bounded inline tool images without fetching URLs or reading paths."""
import base64
import binascii
import copy
import hashlib
import json
import threading
from collections import OrderedDict

from bridge.features.workspace.uploads import image_type

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_IMAGES = 20
MAX_DEPTH = 10
MAX_NODES = 4096
MAX_JSON_CHARS = 32 * 1024 * 1024
# Unscanned values past the budget share this JSON-character allowance per
# output; the rest is replaced so public views never carry unscanned bulk.
MAX_UNSCANNED_CHARS = 16 * 1024
RASTER_TYPES = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp'}


def json_size_within(value, limit, *, ensure_ascii):
    """Count JSON characters up to a limit without materializing the whole value."""
    size = 0
    for chunk in json.JSONEncoder(ensure_ascii=ensure_ascii).iterencode(value):
        size += len(chunk)
        if size > limit:
            return None
    return size


def decode_tool_image(data, mime):
    if (not isinstance(mime, str) or mime not in RASTER_TYPES or not isinstance(data, str)
            or len(data) > ((MAX_IMAGE_BYTES + 2) // 3) * 4):
        return None
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error):
        return None
    return raw if len(raw) <= MAX_IMAGE_BYTES and image_type(raw) == mime else None


def extract_tool_images(output, *, remember=None):
    """Return sanitized output and image descriptors for native or JSON-wrapped MCP results."""
    images, seen_data = [], {}
    total = nodes = parsed_chars = kept = 0
    exhausted = False

    def unscanned(value):
        # One allowance covers every unscanned value in this output, so many
        # small blocks cannot add up to the bulk a single block may not carry.
        nonlocal kept, exhausted
        if not exhausted:
            try:
                size = len(value) if isinstance(value, str) else json_size_within(
                    value, MAX_UNSCANNED_CHARS - kept, ensure_ascii=False)
            except (TypeError, ValueError, RecursionError):
                size = None
            if size is not None and kept + size <= MAX_UNSCANNED_CHARS:
                kept += size
                return value
            exhausted = True
        return {'type': 'omitted', 'reason': 'toolOutputBudget'}

    def walk(value, depth=0):
        nonlocal total, nodes, parsed_chars
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            return unscanned(value)
        if isinstance(value, str):
            candidate = value.lstrip()
            if not candidate.startswith(('{', '[')):
                return value
            if parsed_chars + len(value) > MAX_JSON_CHARS:
                return unscanned(value)
            parsed_chars += len(value)
            try:
                parsed = json.loads(value)
            except (ValueError, RecursionError):
                return value
            clean = walk(parsed, depth + 1)
            return json.dumps(clean, ensure_ascii=False) if clean != parsed else value
        if isinstance(value, list):
            clean = []
            for index, part in enumerate(value):
                if exhausted:
                    # One marker for the rest; per-item markers would outgrow short items.
                    clean.append({'type': 'omitted', 'reason': 'toolOutputBudget', 'items': len(value) - index})
                    break
                clean.append(walk(part, depth + 1))
            return clean
        if not isinstance(value, dict):
            return value
        # Codex rollouts use input_image; app-server dynamic tools use inputImage.
        if value.get('type') in ('image', 'image_url', 'output_image', 'input_image', 'inputImage'):
            data, mime = value.get('data'), value.get('mimeType')
            url = value.get('imageUrl', value.get('image_url', value.get('url')))
            if isinstance(url, dict):
                url = url.get('url')
            if isinstance(url, str) and url.startswith('data:'):
                header, _, data = url.partition(',')
                mime = header[5:-7] if header.endswith(';base64') else None
            elif not isinstance(data, str):
                return value
            placeholder = {'type': 'image', 'preview': 'unavailable'}
            if not isinstance(data, str) or not isinstance(mime, str) or mime not in RASTER_TYPES:
                return placeholder
            known = seen_data.get((mime, data))
            if known is not None:
                return {'type': 'image', 'mimeType': mime, 'preview': known}
            # Base64 length bounds decoded bytes before allocating them. A
            # repeated accepted payload was handled above even at the limit.
            remaining = min(MAX_IMAGE_BYTES, MAX_TOTAL_BYTES - total)
            if (len(images) >= MAX_IMAGES or remaining <= 0 or
                    len(data) > ((remaining + 2) // 3) * 4):
                return placeholder
            raw = decode_tool_image(data, mime)
            if raw is None:
                return placeholder
            identifier = hashlib.sha256(raw).hexdigest()
            if total + len(raw) > MAX_TOTAL_BYTES:
                return placeholder
            seen_data[(mime, data)] = identifier
            if identifier not in (image['desktopId'] for image in images):
                total += len(raw)
                images.append({'type': 'toolImage', 'desktopId': identifier, 'mime': mime,
                               'name': 'Image ' + str(len(images) + 1) + '.' + RASTER_TYPES[mime], 'data': data})
                if remember is not None:
                    remember(identifier, mime, data, raw)
            return {'type': 'image', 'mimeType': mime, 'preview': identifier}
        # Only decode known result envelopes and text content blocks, never arbitrary fields.
        keys = {'content', 'contentItems', 'result'}
        if value.get('type') in ('text', 'output_text', 'input_text', 'inputText'):
            keys.add('text')
        return {key: walk(part, depth + 1) if key in keys else part for key, part in value.items()}

    return walk(output), images


def public_turns(turns, *, image_previews=True):
    """Hide tool-image bytes, and descriptors where previews have no route."""
    def message(row):
        attachments = row.get('attachments')
        if not isinstance(attachments, list) or not any(
                isinstance(a, dict) and a.get('type') == 'toolImage' and
                ('data' in a or not image_previews) for a in attachments):
            return row
        clean = [
            {k: v for k, v in a.items() if k != 'data'}
            if isinstance(a, dict) and a.get('type') == 'toolImage' else a for a in attachments
            if image_previews or not (isinstance(a, dict) and a.get('type') == 'toolImage')]
        return {**row, 'attachments': clean}

    result = []
    for turn in turns:
        messages = [message(row) for row in turn.get('messages', [])]
        changed = any(new is not old for new, old in zip(messages, turn.get('messages', [])))
        result.append({**turn, 'messages': messages} if changed else turn)
    return result


class ToolImageCache:
    """Bounded content cache; callers must separately establish thread membership."""

    def __init__(self, output_bytes=64 * 1024 * 1024, image_bytes=40 * 1024 * 1024,
                 max_entries=256):
        self.output_limit = output_bytes
        self.image_limit = image_bytes
        self.max_entries = max_entries
        self.outputs = OrderedDict()
        self.images = OrderedDict()
        self.output_bytes = self.image_bytes = 0
        self.lock = threading.RLock()

    def _put(self, cache, key, value, size, counter, limit):
        if size > limit or self.max_entries <= 0:
            return
        previous = cache.pop(key, None)
        used = getattr(self, counter) - (previous[1] if previous else 0)
        cache[key] = (value, size)
        used += size
        while used > limit or len(cache) > self.max_entries:
            _, (_, removed) = cache.popitem(last=False)
            used -= removed
        setattr(self, counter, used)

    def _remember(self, identifier, mime, data, raw):
        self._put(self.images, identifier, (mime, data, raw), len(raw) + len(data),
                  'image_bytes', self.image_limit)

    def extract(self, output):
        # Key by content, not mutable item identity: live patches can replace or
        # edit an output in place without changing its tool-call id.
        digest = hashlib.sha256()
        input_size = 0
        encoder = json.JSONEncoder(ensure_ascii=True, separators=(',', ':'))
        for chunk in encoder.iterencode(output):
            input_size += len(chunk)
            if input_size > self.output_limit:
                break
            digest.update(chunk.encode('ascii'))
        key = digest.digest() if input_size <= self.output_limit else None
        with self.lock:
            entry = self.outputs.get(key) if key is not None else None
            if entry is not None:
                self.outputs.move_to_end(key)
                return copy.deepcopy(entry[0])
            result = extract_tool_images(output, remember=self._remember)
            # Conservatively count input plus cached projection and metadata.
            result_size = json_size_within(result, self.output_limit - input_size - 1024,
                                           ensure_ascii=True) if key is not None else None
            size = input_size + result_size + 1024 if result_size is not None else self.output_limit + 1
            if key is not None and size <= self.output_limit:
                self._put(self.outputs, key, copy.deepcopy(result), size,
                          'output_bytes', self.output_limit)
            return result

    def preview(self, attachment):
        identifier, mime, data = attachment['desktopId'], attachment.get('mime'), attachment.get('data')
        # Serialize cold decodes so simultaneous thumbnail/viewer requests share
        # the same bytes. This lock never acquires a session lock.
        with self.lock:
            entry = self.images.get(identifier)
            if entry is not None and entry[0][:2] == (mime, data):
                self.images.move_to_end(identifier)
                return entry[0][2]
            raw = decode_tool_image(data, mime)
            if raw is None or hashlib.sha256(raw).hexdigest() != identifier:
                return None
            self._remember(identifier, mime, data, raw)
            return raw


# The limits cover all loaded chats, including remote hosts. Cached bytes do not
# grant access: each session keeps its own current image index.
TOOL_IMAGE_CACHE = ToolImageCache()

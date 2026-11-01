"""Private bounded-lifetime SDK helper; stdin/stdout are owned by NajdiLab only."""
import json
import sys
import threading

# Fixed codes only. SDK exception text may embed prompts or model output.
REPORTED = {'MODEL_NOT_LOADED', 'MODEL_CHANGED', 'RESULT_MISMATCH', 'NON_TEXT_RESPONSE', 'RESPONSE_TOO_LARGE'}


class LoadedModel:
    def __init__(self, client, sdk, identifier):
        matches = [m for m in client.llm.list_loaded() if m.identifier == identifier]
        if len(matches) != 1:
            raise ValueError('MODEL_NOT_LOADED')
        self.sdk = sdk
        self.identity = matches[0].get_info().instance_reference
        if not isinstance(self.identity,str) or not self.identity:
            raise ValueError('INSTANCE_REFERENCE_REQUIRED')
        self.specifier = {'type':'instanceReference','instanceReference':self.identity}
        # list_loaded handles are symbolic: SDK 1.5 re-resolves their identifier
        # on every call. Public handle methods forward `identifier` unchanged as
        # an AnyModelSpecifier, so this one can only ever reach this instance;
        # no identifier fallback or get-or-load operation is permitted.
        self.model = sdk.LLM(self.specifier, client.llm)
        self.stream = None

    def limits(self):
        info = self.model.get_info()
        context = self.model.get_context_length()
        return {'budget_ceiling':context, 'model_max_context':info.max_context_length, 'runtime_context':context,
                'architecture':info.architecture, 'weights_bytes':info.size_bytes, 'quantization':None, 'kv':None,
                'loaded':{'context':context, 'size_bytes':None, 'size_vram_bytes':None}, 'other_loaded_models':[],
                'model_key':info.model_key, 'engine_version':None}

    def measure(self, messages):
        if not messages or any(set(m) != {'role','content'} or m['role'] not in {'user','assistant'} or not isinstance(m['content'], str) for m in messages):
            raise ValueError('INVALID_HISTORY')
        if [m['role'] for m in messages] != ['user' if i % 2 == 0 else 'assistant' for i in range(len(messages))] or len(messages) % 2 != 1:
            raise ValueError('INVALID_HISTORY')
        self.history = self.sdk.Chat.from_history({'messages':messages})
        self.template = self.model.apply_prompt_template(self.history)
        if not isinstance(self.template,str) or not self.template:
            raise ValueError('INVALID_TEMPLATE')
        self.tokens = self.model.tokenize(self.template)
        if not isinstance(self.tokens,(list,tuple)) or not 0 < len(self.tokens) <= 1048576 or any(type(x) is not int or x < 0 for x in self.tokens):
            raise ValueError('INVALID_TOKENS')
        self.context = self.model.get_context_length()
        return {'input_tokens':len(self.tokens), 'loaded_context':self.context,
                'model_key':self.model.get_info().model_key,'instance_reference':self.identity}

    def cancel(self):
        if self.stream is not None:
            self.stream.cancel()

    def generate(self, reserve, stop):
        if (self.model.get_info().instance_reference != self.identity or
            self.model.get_context_length() != self.context or
            self.model.apply_prompt_template(self.history) != self.template or
            list(self.model.tokenize(self.template)) != list(self.tokens)):
            raise ValueError('MODEL_CHANGED')
        if stop.is_set():
            raise ValueError('STOPPED')
        # No preset, system message, tools, retrieval, formatting or load config.
        # Engine/template defaults are retained; overflow can never roll history.
        with self.model.respond_stream(self.history, config={
            'maxTokens':reserve, 'contextOverflowPolicy':'stopAtLimit', 'rawTools':{'type':'none'}
        }) as stream:
            self.stream = stream
            fragments, size = [], 0
            for fragment in stream:
                if stop.is_set():
                    stream.cancel()
                    raise ValueError('STOPPED')
                # Reasoning is not a final answer. Refuse rather than silently
                # editing a mixed result into a training target.
                if getattr(fragment, 'reasoning_type', 'none') != 'none':
                    stream.cancel()
                    raise ValueError('NON_TEXT_RESPONSE')
                size += len(fragment.content.encode('utf-8'))
                if size > 262144:
                    stream.cancel()
                    raise ValueError('RESPONSE_TOO_LARGE')
                fragments.append(fragment.content)
            result = stream.result()
        if (self.model.get_info().instance_reference != self.identity or result.structured or
            result.content != ''.join(fragments) or result.stats.prompt_tokens_count != len(self.tokens)):
            raise ValueError('RESULT_MISMATCH')
        return {'content':result.content, 'input_tokens':result.stats.prompt_tokens_count,
                'output_tokens':result.stats.predicted_tokens_count, 'stop_reason':result.stats.stop_reason}


def read():
    raw = sys.stdin.buffer.readline(2 * 1024 * 1024 + 1)
    if not raw or len(raw) > 2 * 1024 * 1024:
        raise ValueError('INVALID_INPUT')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('INVALID_INPUT')
    return value


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    try:
        import lmstudio as sdk
        from importlib.metadata import version
        if version('lmstudio') != '1.5.0':
            raise ImportError('Pinned SDK required')
    except ImportError:
        emit({'error':'SDK_REQUIRED'})
        return
    try:
        setup = read()
        port = setup['port']
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('INVALID_PORT')
        # This is the gap allowed between SDK messages, and a long prompt sends
        # none while it is processed. The parent enforces the same total limit.
        sdk.set_sync_api_timeout(setup['deadline'])
        # An explicit numeric host avoids discovery/port scans. list_loaded
        # returns existing handles; `.model()` would auto-load and is forbidden.
        with sdk.Client(f'127.0.0.1:{port}') as client:
            loaded = LoadedModel(client, sdk, setup['model'])
            request = read()
            if request.get('limits'):
                emit(loaded.limits())
                return
            emit(loaded.measure(request['messages']))
            command = read()
            if command.get('stop'):
                return
            reserve = command['reply_reserve']
            if type(reserve) is not int or not 1 <= reserve <= 8192:
                raise ValueError('INVALID_RESERVE')
            stopped = threading.Event()
            def controls():
                try:
                    read()
                finally:
                    stopped.set()
                    loaded.cancel()
            threading.Thread(target=controls, daemon=True).start()
            emit(loaded.generate(reserve, stopped))
    except ValueError as error:
        emit({'error':str(error) if str(error) in REPORTED else 'ENGINE_UNAVAILABLE'})
    except Exception:
        # Never expose the SDK exception: it may embed prompts or model output.
        emit({'error':'ENGINE_UNAVAILABLE'})


if __name__ == '__main__':
    main()

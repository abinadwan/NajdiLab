"""Private bounded-lifetime SDK helper; stdin/stdout are owned by NajdiLab only."""
import json
import sys
import threading


class LoadedModel:
    def __init__(self, client, sdk, identifier):
        matches = [m for m in client.llm.list_loaded() if m.identifier == identifier]
        if len(matches) != 1:
            raise ValueError('MODEL_NOT_LOADED')
        self.model, self.sdk = matches[0], sdk
        self.identity = self.model.get_info().instance_reference
        if not isinstance(self.identity,str) or not self.identity:
            raise ValueError('INSTANCE_REFERENCE_REQUIRED')
        self.session = client.llm
        self.specifier = {'type':'instanceReference','instanceReference':self.identity}
        self.stream = None

    def measure(self, messages):
        if not messages or any(set(m) != {'role','content'} or m['role'] not in {'user','assistant'} or not isinstance(m['content'], str) for m in messages):
            raise ValueError('INVALID_HISTORY')
        if [m['role'] for m in messages] != ['user' if i % 2 == 0 else 'assistant' for i in range(len(messages))] or len(messages) % 2 != 1:
            raise ValueError('INVALID_HISTORY')
        self.history = self.sdk.Chat.from_history({'messages':messages})
        # SDK 1.5 symbolic handles resolve an identifier on every call. Bind
        # the existing protocol helpers to an immutable instance reference;
        # no identifier fallback or get-or-load operation is permitted.
        self.template = self.session._apply_prompt_template(self.specifier,self.history)
        if not isinstance(self.template,str) or not self.template:
            raise ValueError('INVALID_TEMPLATE')
        self.tokens = self.session._tokenize(self.specifier,self.template)
        if not isinstance(self.tokens,(list,tuple)) or not 0 < len(self.tokens) <= 1048576 or any(type(x) is not int or x < 0 for x in self.tokens):
            raise ValueError('INVALID_TOKENS')
        self.context = self.session._get_context_length(self.specifier)
        return {'input_tokens':len(self.tokens), 'loaded_context':self.context,
                'model_key':self.session.get_model_info(self.specifier).model_key,'instance_reference':self.identity}

    def cancel(self):
        if self.stream is not None:
            self.stream.cancel()

    def generate(self, reserve, stop):
        if (self.session.get_model_info(self.specifier).instance_reference != self.identity or
            self.session._get_context_length(self.specifier) != self.context or
            self.session._apply_prompt_template(self.specifier,self.history) != self.template or
            list(self.session._tokenize(self.specifier,self.template)) != list(self.tokens)):
            raise ValueError('MODEL_CHANGED')
        if stop.is_set():
            raise ValueError('STOPPED')
        # No preset, system message, tools, retrieval, formatting or load config.
        # Engine/template defaults are retained; overflow can never roll history.
        with self.session._respond_stream(self.specifier,self.history, config={
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
        if (self.session.get_model_info(self.specifier).instance_reference != self.identity or result.structured or
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
        sdk.set_sync_api_timeout(15)
        # An explicit numeric host avoids discovery/port scans. list_loaded
        # returns existing handles; `.model()` would auto-load and is forbidden.
        with sdk.Client(f'127.0.0.1:{port}') as client:
            loaded = LoadedModel(client, sdk, setup['model'])
            emit(loaded.measure(read()['messages']))
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
    except Exception:
        # Never expose the SDK exception: it may embed prompts or model output.
        emit({'error':'ENGINE_UNAVAILABLE'})


if __name__ == '__main__':
    main()

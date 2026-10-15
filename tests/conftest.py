"""Test-only Twilio fallback for disconnected CI environments.
Real Twilio SDK is used automatically when installed from requirements.txt.
"""
import base64
import hashlib
import hmac
import sys
import types

try:
    import twilio
except ImportError:
    mod = types.ModuleType('twilio')
    rest = types.ModuleType('twilio.rest')
    req = types.ModuleType('twilio.request_validator')
    vr = types.ModuleType('twilio.twiml.voice_response')
    twiml = types.ModuleType('twilio.twiml')

    class RequestValidator:
        def __init__(self, token): self.token = token
        def validate(self, url, params, signature):
            message = url + ''.join(str(k) + str(v) for k, v in sorted(params.items()))
            expected = base64.b64encode(hmac.new(self.token.encode(), message.encode(), hashlib.sha1).digest()).decode()
            return hmac.compare_digest(expected, signature or '')

    class Client:
        def __init__(self, *args, **kwargs): pass

    class VoiceResponse:
        def __init__(self): self.content = ''
        def connect(self): return self
        def stream(self, url): self.content += f'<Connect><Stream url="{url}">'; return self
        def parameter(self, name, value): self.content += f'<Parameter name="{name}" value="{value}"/>'
        def say(self, message): self.content += f'<Say>{message}</Say>'
        def __str__(self): return '<Response>' + self.content + ('</Stream></Connect>' if '<Stream' in self.content else '') + '</Response>'

    mod.rest = rest; rest.Client = Client; req.RequestValidator = RequestValidator
    vr.VoiceResponse = VoiceResponse
    sys.modules.update({'twilio':mod,'twilio.rest':rest,'twilio.request_validator':req,
                        'twilio.twiml':twiml,'twilio.twiml.voice_response':vr})

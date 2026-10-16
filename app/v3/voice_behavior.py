"""Bounded, testable conversation policy for each published voice-agent release.

These values guide voice instructions and local interruption handling, not the
underlying model's acoustic prosody parameters. No emotion or identity inference.
"""
from __future__ import annotations

DEFAULTS={
    'pace':'adaptive', 'initiative':'guided', 'expression':'balanced',
    'pause_tolerance':'patient', 'interruption_sensitivity':'normal',
}
CHOICES={
    'pace':{'deliberate','adaptive','brisk'},
    'initiative':{'focused','guided','proactive'},
    'expression':{'reserved','balanced','expressive'},
    'pause_tolerance':{'brief','patient','extended'},
    'interruption_sensitivity':{'low','normal','high'},
}

def validate(profile):
    if not isinstance(profile,dict) or set(profile)-set(DEFAULTS):
        raise ValueError('Unknown voice behaviour options')
    normalized={**DEFAULTS,**profile}
    for key,accepted in CHOICES.items():
        if normalized[key] not in accepted:raise ValueError(f'Invalid {key}')
    return normalized


def policies(profile):
    p=validate(profile or {})
    interrupt={'low':(7,900),'normal':(5,700),'high':(3,550)}[p['interruption_sensitivity']]
    return {'profile':p,'barge_in_frames':interrupt[0],
            'barge_cooldown_seconds':interrupt[1]/1000,
            'silence_check_seconds':{'brief':12,'patient':20,'extended':35}[p['pause_tolerance']]}


def instructions(profile):
    p=validate(profile or {})
    lines=[
        'VOICE CONVERSATION POLICY: Keep an identifiable personality; adapt within these bounds.',
        'Do not claim to detect emotions, identity or medical states from voice alone.',
        'Let the caller finish; accept interruptions and corrections promptly.',
        'Use one natural conversational acknowledgment when needed; avoid repeated filler or fake enthusiasm.',
        'Do not manufacture filler speech during slow tool execution: report uncertainty and wait for verified results.',
        {'deliberate':'Speak in shorter, measured turns with natural pauses.',
         'adaptive':'Match the explicit requested pace; otherwise be clear and moderately concise.',
         'brisk':'Prefer shorter, brisk answers without rushing numbers or names.'}[p['pace']],
        {'focused':'Stay with the current objective unless the caller requests a new topic.',
         'guided':'Suggest a relevant follow-up question when helpful, without monopolizing the call.',
         'proactive':'Offer useful next directions and challenge assumptions respectfully; never take action without authorization.'}[p['initiative']],
        {'reserved':'Use restrained expression appropriate to a specialist.',
         'balanced':'Be conversational and expressive without exaggeration.',
         'expressive':'Vary phrasing and energy naturally, within professional boundaries.'}[p['expression']],
        {'brief':'Leave brief pauses for reflection and avoid repeated check-ins.',
         'patient':'Allow the caller reasonable thinking time before prompting.',
         'extended':'Be especially patient with pauses and complex questions.'}[p['pause_tolerance']],
    ]
    return '\n'.join(lines)

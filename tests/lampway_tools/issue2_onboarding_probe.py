# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded GUI transition checks shared by the native fixture and falsifiers."""
WORDS = {2: 'Every route is off until', 3: 'The agent thinks with the provider',
         4: 'OpenRouter, in dollars'}


class OnboardingProbe:
    """Await handled input and its rendered panel without accepting persistent staleness."""
    def __init__(self, expected, previous, started, footer=None, timeout=10):
        self.expected = expected
        self.previous = previous
        self.deadline = started + timeout
        self.footer = footer
        self.samples = []

    def observe(self, widgets, model_step, now):
        texts = [w.get('text', '') for w in widgets]
        shown = [n for n, word in WORDS.items() if any(t.startswith(word) for t in texts)]
        assert len(shown) == 1, ('overlapping or missing onboarding panel', shown, texts)
        assert shown[0] in (self.previous, self.expected), ('unexpected onboarding panel', shown)
        continues = [w['rect'] for w in widgets if w.get('text', '').startswith('Continue')]
        backs = [w['rect'] for w in widgets if w.get('text') == 'Back']
        assert len(continues) == len(backs) == 1, ('duplicate or missing onboarding footer', backs, continues)
        footer = (backs[0], continues[0])
        assert abs(sum(backs[0][1::2]) - sum(continues[0][1::2])) <= 2, ('Back must share Continue footer', footer)
        if self.footer is None:
            self.footer = footer
        assert footer == self.footer, ('onboarding footer moved', self.footer, footer)
        assert model_step in (self.previous, self.expected), ('unexpected onboarding model step', model_step)
        ready = model_step == self.expected and shown == [self.expected]
        self.samples.append({'at': now, 'model_step': model_step, 'shown': shown,
                             'back': backs[0], 'continue': continues[0]})
        assert ready or now < self.deadline, ('onboarding transition timeout', self.expected,
            'input not handled' if model_step != self.expected else 'stale rendered panel', self.samples)
        return ready, texts, footer

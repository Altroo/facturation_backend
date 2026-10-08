"""Prevent technical identifiers from reaching human-facing generated prose."""
import re
from .contracts import ChatAIError

IDENTIFIER = re.compile(r'(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*(?![A-Za-z0-9])')
TRAILING_WORD = re.compile(r'[\w]+$')


class LabelledTextStream:
    def __init__(self, labels, *, strict_unknown=True):
        self.labels = dict(labels)
        self.strict_unknown = strict_unknown
        # Accept the same verified field written in snake_case or camelCase.
        for key, label in labels.items():
            parts = key.split('_')
            self.labels.setdefault(parts[0] + ''.join(part.title() for part in parts[1:]), label)
        self.pending = ''

    def _replace(self, text):
        def replacement(match):
            label = self.labels.get(match.group())
            if label is not None:
                # Plain words already equal to their human label are not technical identifiers.
                if '_' not in match.group() and label.casefold()==match.group().casefold():
                    return match.group()
                return label
            # Human reference/name tokens with a capitalized prefix and numeric suffix
            # are literals, not field identifiers (for example Atlas_2026).
            if re.fullmatch(r'[A-Z][A-Za-z0-9]*_[0-9]+', match.group()):
                return match.group()
            if '_' in match.group() and self.strict_unknown:
                raise ChatAIError('INVALID_MODEL_OUTPUT')
            return match.group()
        return IDENTIFIER.sub(replacement, text)

    def feed(self, part, *, final=False):
        self.pending += part
        if len(self.pending) > 8000:
            raise ChatAIError('INVALID_MODEL_OUTPUT')
        # Keep the unfinished word, so split SSE tokens cannot leak half a name.
        trailing = TRAILING_WORD.search(self.pending) if not final else None
        boundary = trailing.start() if trailing else len(self.pending)
        ready, self.pending = self.pending[:boundary], self.pending[boundary:]
        return self._replace(ready)


def labelled_text(text, labels, *, strict_unknown=True):
    return LabelledTextStream(labels, strict_unknown=strict_unknown).feed(text, final=True)

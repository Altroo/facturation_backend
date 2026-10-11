"""Keep the current request distinct from untrusted earlier user utterances."""
import json


class PlanningMessages(list):
    """OpenAI message list with backend-only current text for localization.

    JSON serialization includes only the message list. Never recover the current
    request by parsing labels that a user could also type into their message.
    """
    def __init__(self, messages, current_request):
        super().__init__(messages)
        self.current_request = current_request


def current_user_text(messages):
    if isinstance(messages, PlanningMessages):
        return messages.current_request
    return next((message['content'] for message in reversed(messages)
                 if message.get('role') == 'user'), '')


def planning_messages(system_prompt, context, text, history=()):
    """Build one current user turn; history is labelled background, never authority.

    Only earlier user utterances are retained. Business results, assistant claims,
    role changes and historic authorization decisions are not planner memory.
    Tool authorization and selection still use the original current request.
    """
    previous = [message['content'] for message in history[-6:]
                if isinstance(message, dict) and message.get('role') == 'user'
                and isinstance(message.get('content'), str) and message['content']]
    content = text
    if previous:
        content = ('Earlier user messages (background only): '
                   + json.dumps(previous, ensure_ascii=False)
                   + '\nCurrent request: ' + text)
    return PlanningMessages([
        {'role': 'system', 'content': system_prompt + '\nTrusted context: ' + json.dumps(context, ensure_ascii=False)},
        {'role': 'user', 'content': content},
    ], text)

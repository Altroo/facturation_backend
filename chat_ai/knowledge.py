import math
import re
from collections import Counter
import unicodedata
from django.db.models import Q
from .models import KnowledgeDocument
from .security import SECRET


LOCALIZED_CONTENT_LIMIT = 6000


def validate_localized_content(value):
    """Validate reviewed excerpts, without accepting arbitrary locale metadata."""
    if not isinstance(value, dict) or set(value) != {'fr', 'en'}:
        raise ValueError('Expected exactly French and English excerpts.')
    for text in value.values():
        if (not isinstance(text, str) or not text.strip()
                or len(text) > LOCALIZED_CONTENT_LIMIT or '\x00' in text
                or SECRET.search(text)):
            raise ValueError('Invalid or sensitive localized excerpt.')
    return dict(value)


def localized_content_for_retrieval(value):
    # Legacy documents use {}. Invalid direct database edits must not be served.
    try:
        return validate_localized_content(value)
    except ValueError:
        return {}


# Function words and generic question scaffolding carry no workflow identity.
# Domain/action words (create, find, delete, payment, etc.) remain searchable.
STOP_WORDS = frozenset("""
a an and are as at be been between by can could do does for from how i in is it
its me my of on or our please should tell than that the their them there these
they this those to us was we were what when where which who why will with would
you your explain show about
au aux avec ce ces cet cette chez comment dans de des du elle elles en entre est
et eux il ils je la le les leur leurs lui ma mais me mes moi mon ne nos notre
nous on ou par pas peut peux pour pourquoi quand que quel quelle quelles quels
qui sa se ses si son sont sous sur ta te tes toi ton tu un une vos votre vous
explique expliquez merci veuillez l d j c t s m n qu
""".split())


def singular(word):
    # Small morphological rules only; no query-to-document routing or synonyms.
    if word == 'statuses':
        return 'status'
    if len(word) > 4 and word.endswith('ies'):
        return word[:-3] + 'y'
    if len(word) > 5 and word.endswith(('sses', 'ches', 'shes', 'xes', 'zes')):
        return word[:-2]
    if len(word) > 4 and word.endswith('eaux'):
        return word[:-1]
    if len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is', 'ics')):
        return word[:-1]
    return word


def tokens(text):
    folded = ''.join(char for char in unicodedata.normalize('NFKD', text.casefold())
                     if not unicodedata.combining(char))
    words = re.findall(r"[^\W_]+", folded, re.UNICODE)
    return {singular(word) for word in words if word not in STOP_WORDS}



class ChatAIKnowledgeService:
    @staticmethod
    def sources_authorized(sources, company_id, capabilities):
        if not isinstance(sources, list) or not 1 <= len(sources) <= 3:
            return False
        if any(not isinstance(source, dict) or set(source) != {'document_id', 'version'}
               or not isinstance(source['document_id'], str) or not source['document_id']
               or not isinstance(source['version'], str) or not source['version'] for source in sources):
            return False
        expected = {source['document_id']: source['version'] for source in sources}
        if len(expected) != len(sources):
            return False
        authorized = KnowledgeDocument.objects.filter(
            document_id__in=expected, application_id='facturation', sensitivity='member',
            required_capabilities__contained_by=list(capabilities),
        ).filter(Q(tenant_scope__isnull=True) | Q(tenant_scope_id=company_id))
        return dict(authorized.values_list('document_id', 'document_version')) == expected

    def retrieve(self, query, company_id, capabilities):
        # Restrict BEFORE reading titles/content or ranking. No cross-tenant corpus cache.
        qs = KnowledgeDocument.objects.filter(application_id='facturation', sensitivity='member', required_capabilities__contained_by=list(capabilities)).filter(Q(tenant_scope__isnull=True) | Q(tenant_scope_id=company_id))
        words = tokens(query)
        if not words:
            return []
        documents = []
        frequencies = Counter()
        for doc in qs.order_by('document_id')[:200]:
            if not set(doc.required_capabilities) <= set(capabilities):
                continue
            keywords = tokens(' '.join(doc.keywords))
            title, content = tokens(doc.title), tokens(doc.content)
            documents.append((doc, keywords, title, content))
            frequencies.update(keywords | title | content)
        # Specific topic words outweigh vocabulary shared by many workflows.
        # Document frequency is computed ONLY from this authorized corpus.
        weights = {word: math.log1p(len(documents) / frequencies[word])
                   for word in words if frequencies[word]}
        hits = []
        for doc, keywords, title, content in documents:
            score = sum(weight * (3 * (word in keywords) + 2 * (word in title)
                                  + 0.5 * (word in content))
                        for word, weight in weights.items())
            if score:
                hits.append((score, {'document_id': doc.document_id, 'version': doc.document_version,
                                     'title': doc.title, 'content': doc.content[:3500],
                                     'localized_content': localized_content_for_retrieval(doc.localized_content)}))
        return [item for _, item in sorted(hits, key=lambda x: -x[0])[:3]]

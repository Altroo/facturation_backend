"""Optional user-facing shortcuts; names/descriptions never stand in for record IDs."""
import re

NUMBER = re.compile(r"^\d{1,10}/\d{2,4}$")
from .shortcut_catalog import ALIASES, MODULES, permitted_commands, shortcut_catalog, usage

USAGE = {item['command']: usage(item['command']) for item in shortcut_catalog()}


def shortcut_action(text, executor=None, interface_language='fr'):
    if not text.startswith('/'):
        return None
    parts = text.split(maxsplit=1)
    command = ALIASES.get(parts[0].casefold(), parts[0].casefold())
    argument = parts[1].strip() if len(parts) == 2 else ''

    def action(tool, usage=None, **args):
        result = {'tool': tool, 'arguments': args}
        if usage:
            result['usage_message'] = usage
        return result

    def clarify(message):
        return {'tool': 'clarify', 'message': message}

    from chat_ai_assistant.clarifications import message_language
    language = message_language(text, interface_language)
    if command not in permitted_commands(executor):
        if command in USAGE:
            from chat_ai_assistant.contracts import ChatAIError
            raise ChatAIError('PERMISSION_DENIED')
        return clarify('Unknown command. Send /help to see available shortcuts.' if language == 'en' else 'Commande inconnue. Envoyez /aide pour afficher les raccourcis disponibles.')
    command_usage = usage(command, executor, language) if command != '/help' else ''
    if command == '/help':
        intro = ('Shortcuts describe what you want to do. You can also write normally.\n' if language == 'en' else 'Les raccourcis indiquent ce que vous voulez faire. Vous pouvez aussi écrire normalement.\n')
        return clarify(intro + '\n'.join(f"{item['command']} : {item['title']}" for item in shortcut_catalog(executor, language)) + ('\nSend a command alone for usage and an example.' if language == 'en' else '\nEnvoyez une commande seule pour voir son utilisation et un exemple.'))
    for module in MODULES:
        if command == module[0] and command not in ('/clients', '/factures', '/paiements'):
            return None if argument else action(module[3], usage=command_usage, **module[4])
    if not argument and command in ('/voir', '/pdf', '/modifier', '/supprimer', '/bilan'):
        return clarify(command_usage)
    if command == '/factures':
        return None if argument else action('search_invoices', usage=command_usage)
    if command == '/impayees':
        return None if argument else action('search_invoices', usage=command_usage, unpaid=True)
    if command == '/clients':
        return action('search_clients', usage=command_usage if not argument else None, query=argument)
    if command == '/paiements':
        return None if argument else action('list_payments', usage=command_usage)
    if command == '/voir':
        return action('search_invoices', invoice_number=argument) if NUMBER.fullmatch(argument) else None
    if command == '/pdf':
        return action('invoice_pdf', invoice_number=argument) if NUMBER.fullmatch(argument) else None
    if command == '/supprimer':
        return action('prepare_change', resource='invoice', invoice_number=argument, operation='delete') if NUMBER.fullmatch(argument) else None
    if command == '/modifier':
        fields = argument.split(' ', 2)
        if not NUMBER.fullmatch(fields[0]):
            return None
        if len(fields) == 1:
            return action('navigate', resource='invoice_edit', invoice_number=fields[0])
        # Users name the field as it appears on the form. Unknown prose goes to
        # the planner, never into an invoice-number argument.
        remainder = argument[len(fields[0]):].strip()
        labels = {
            'remarque': 'remarque', 'remark': 'remarque',
            'termes de paiement': 'termes_paiement', 'payment terms': 'termes_paiement',
            'date d’échéance': 'date_echeance', "date d'échéance": 'date_echeance',
            'due date': 'date_echeance',
            'termes_paiement': 'termes_paiement', 'date_echeance': 'date_echeance',
        }
        for label, field in labels.items():
            match = re.match(re.escape(label) + r'(?:\s*:\s*|\s+)(.+)$', remainder, re.IGNORECASE)
            if match:
                return action('prepare_change', resource='invoice', invoice_number=fields[0],
                              operation='update', changes={field: match.group(1).strip()})
        return None
    if command == '/bilan':
        fields = argument.split()
        metrics = {'facture': 'invoiced_net_ttc', 'encaissements': 'collected', 'solde': 'outstanding', 'nombre': 'invoice_count'}
        periods = {'mois': 'current_month', 'année': 'current_year', 'annee': 'current_year', 'mois-precedent': 'previous_month', 'annee-precedente': 'previous_year'}
        if len(fields) not in (2, 3) or fields[0] not in metrics or fields[1] not in periods:
            return clarify(command_usage)
        return action('financial_summary', metric=metrics[fields[0]], period=periods[fields[1]], currency=fields[2].upper() if len(fields) == 3 else 'MAD')
    return clarify('Commande inconnue. Envoyez /aide pour afficher les raccourcis disponibles et leur utilisation.')



def reference_action(text, references):
    """Resolve only exact positional requests against existing conversation state.

    This selects the existing authorized tool, never an identifier or queryset.
    Additional predicates, resource names, negation and compound requests stay
    with the planner instead of silently losing part of the user's instruction.
    """
    if not references.get('ids'):
        return None
    from chat_ai_assistant.routing import normalized
    words = re.sub(r"\s+", ' ', normalized(text)).strip().rstrip('.!?').strip()
    ordinals = {
        'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
        'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
        'premier': 1, 'premiere': 1, 'deuxieme': 2, 'troisieme': 3,
        'quatrieme': 4, 'cinquieme': 5, 'sixieme': 6, 'septieme': 7,
        'huitieme': 8, 'neuvieme': 9, 'dixieme': 10,
    }
    order = '|'.join(ordinals) + r'|10(?:th|e)?|[1-9](?:st|nd|rd|th|er|re|e)?'
    patterns = (
        rf'(?:please )?open (?:the )?({order})(?: result| one)(?: please)?',
        rf'(?:please )?open (?:the )?result ({order})(?: please)?',
        rf'(?:ouvre|ouvrez) (?:le|la) ({order})(?: resultat)?(?: svp)?',
        rf'(?:ouvre|ouvrez) (?:le )?resultat ({order})(?: svp)?',
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, words)
        if match:
            ordinal = match.group(1)
            index = ordinals[ordinal] if ordinal in ordinals else int(re.match(r'\d+', ordinal).group())
            return {'tool': 'previous_results', 'arguments': {'operation': 'open', 'index': index}}
    if references.get('resource') == 'invoice' and words in {
        'which ones are unpaid', 'which of these are unpaid',
        'lesquelles sont impayees', 'lesquels sont impayes',
        'quelles sont les impayees',
    }:
        return {'tool': 'previous_results', 'arguments': {'operation': 'unpaid'}}
    return None



def knowledge_action(text):
    """Route explicit general help to approved retrieval without a planning pass.

    Business-data questions, specific record references and compound actions stay
    with the model. Knowledge retrieval still enforces the current user's rights.
    """
    from chat_ai_assistant.routing import normalized
    words = re.sub(r"\s+", ' ', normalized(text)).strip().rstrip('.!?').strip()
    if (len(text) > 300 or re.search(r'\d', words)
            or re.search(r"\b(?:then|puis|ensuite|ignore|oublie|and|et|this|that|these|those|its|their|cette|cet|ce|ces|son|sa|ses|celle|celui|celles|ceux|current|selected)\b|[;\n]|\b\w+['’]s\b", text.casefold())):
        return None
    procedure = re.match(r'^(?:please )?(?:how do (?:i|we) |how to |comment (?:creer|trouver|rechercher|valider|modifier|supprimer|utiliser|ouvrir)\b)', words)
    definition = re.fullmatch(r'(?:please )?what does .+ mean|que signifie .+|que veut dire .+', words)
    general_words = set('please explain explique expliquez the a an of for le la les un une des de du d invoice invoices facture factures client clients customer customers document documents payment payments paiement paiements stock form forms formulaire formulaires status statuses statut statuts field fields champ champs label labels libelle libelles workflow workflows procedure procedures ht tva ttc vat'.split())
    explanation = (set(re.findall(r'[a-z]+', words)) <= general_words
                   and re.match(r'^(?:please )?(?:explain|explique|expliquez)\b', words)
                   and re.search(r'\b(?:statuses|status|statut|statuts|fields|field|champ|champs|labels|label|libelle|libelles|workflow|workflows|procedure|procedures|ht|tva|ttc|vat)\b', words))
    if procedure or definition or explanation:
        return {'tool': 'knowledge', 'arguments': {'query': text.strip()}}
    return None

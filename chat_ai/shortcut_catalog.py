"""Permission-filtered shortcut metadata for existing Facturation tools only."""
from chat_ai_assistant.contracts import ChatAIError

# command, native capability, resource, search tool/arguments, labels and examples.
MODULES = (
    ('/factures', 'read', 'invoices', 'search_invoices', {}, 'Factures client', 'Customer invoices', 'du client Atlas', 'for customer Atlas'),
    ('/devis', 'read', 'quotes', 'search_quotes', {}, 'Devis', 'Quotes', 'du client Atlas avec peinture', 'for customer Atlas with paint'),
    ('/proformas', 'read', 'proformas', 'search_documents', {'resource':'proforma'}, 'Factures pro forma', 'Pro forma invoices', 'du client Atlas', 'for customer Atlas'),
    ('/avoirs', 'read', 'credit_notes', 'search_documents', {'resource':'credit_note'}, 'Factures d’avoir', 'Credit notes', 'du client Atlas', 'for customer Atlas'),
    ('/livraisons', 'read', 'delivery_notes', 'search_documents', {'resource':'delivery_note'}, 'Bons de livraison', 'Delivery notes', 'du client Atlas', 'for customer Atlas'),
    ('/clients', 'read', 'clients', 'search_clients', {'query':''}, 'Clients', 'Customers', 'Atlas', 'Atlas'),
    ('/articles', 'read', 'articles', 'search_articles', {}, 'Articles', 'Articles', 'peinture', 'paint'),
    ('/paiements', 'read', 'payments', 'list_payments', {}, 'Règlements', 'Payments', '', ''),
    ('/stock', 'stock_read', 'stock', 'search_operations', {'resource':'stock_balance'}, 'Stock', 'Stock', 'peinture à Casablanca', 'paint in Casablanca'),
    ('/mouvements', 'stock_read', 'stock_movements', 'search_operations', {'resource':'stock_movement'}, 'Mouvements de stock', 'Stock movements', 'de peinture', 'for paint'),
    ('/receptions', 'stock_read', 'stock_receipts', 'search_operations', {'resource':'stock_receipt'}, 'Réceptions de stock', 'Stock receipts', 'de peinture', 'for paint'),
    ('/inventaires', 'stock_read', 'stock_inventories', 'search_operations', {'resource':'stock_inventory'}, 'Inventaires', 'Inventories', 'à Casablanca', 'in Casablanca'),
    ('/logistique', 'read', 'logistics', 'search_operations', {'resource':'logistics_order'}, 'Logistique', 'Logistics', 'du client Atlas avec peinture', 'for customer Atlas with paint'),
    ('/utilisateurs', 'user_admin', 'users', 'search_users', {}, 'Utilisateurs', 'Users', 'Samira', 'Samira'),
)

ALIASES = {
    '/chercher':'/voir', '/impayées':'/impayees', '/reglements':'/paiements',
    '/proforma':'/proformas', '/logistiques':'/logistique', '/logistics':'/logistique',
    '/réceptions':'/receptions', '/users':'/utilisateurs', '/quotes':'/devis',
    '/invoices':'/factures', '/customers':'/clients', '/payments':'/paiements',
    '/inventories':'/inventaires', '/receipts':'/receptions', '/movements':'/mouvements',
    '/aide':'/help',
}

EXTRA = (
    ('/voir', 'read', 'Rechercher des documents', 'Search documents',
     'Décrivez le type de document, le client, le produit ou la période. Choisissez parmi les résultats; aucun identifiant technique à retenir.',
     'Describe the document, customer, product or period. Select a result; you do not need an internal identifier.',
     'devis du client Atlas avec peinture', 'quotes for customer Atlas with paint'),
    ('/impayees', 'read', 'Factures impayées', 'Unpaid invoices',
     'Affiche les factures avec un solde restant pour la société active.', 'Lists invoices with an outstanding balance in the active company.', '', ''),
    ('/bilan', 'read', 'Synthèse financière', 'Financial summary',
     'Précisez la mesure : facture, encaissements, solde ou nombre; et la période : mois, annee, mois-precedent ou annee-precedente. Devise facultative : MAD, EUR ou USD.',
     'Specify the metric: facture (invoiced), encaissements (collected), solde (outstanding) or nombre (count); and period: mois, annee, mois-precedent or annee-precedente. Optional currency: MAD, EUR or USD.',
     'encaissements mois MAD', 'encaissements mois MAD'),
    ('/pdf', 'print', 'Télécharger un document', 'Download a document',
     'Recherchez le document puis choisissez PDF dans les résultats, selon vos droits d’impression.', 'Find the document and choose PDF in the results, subject to your print permissions.', 'facture du client Atlas', 'invoice for customer Atlas'),
    ('/modifier', 'update', 'Modifier un document ou client', 'Edit a document or customer',
     'Recherchez puis sélectionnez le résultat. Les changements pris en charge demandent confirmation et conservent votre historique.', 'Find and select the result. Supported changes require confirmation and retain your actor history.', 'facture du client Atlas', 'invoice for customer Atlas'),
    ('/supprimer', 'delete', 'Supprimer un document ou client', 'Delete a document or customer',
     'Recherchez, sélectionnez puis confirmez. Aucune suppression sans vérification des droits et confirmation.', 'Find, select and confirm. Deletion always requires permission checks and confirmation.', 'devis du client Atlas', 'quote for customer Atlas'),
)


def permitted_commands(executor=None):
    if executor is None:
        return {m[0] for m in MODULES} | {m[0] for m in EXTRA} | {'/help'}
    context = executor.authorize_context()
    caps = set(executor.capabilities())
    from core.permissions import can_print, can_update, can_delete
    if context.membership is not None:
        for capability, check in (('print', can_print), ('update', can_update), ('delete', can_delete)):
            if check(context.user, executor.company_id): caps.add(capability)
    return {m[0] for m in MODULES if m[1] in caps} | {m[0] for m in EXTRA if m[1] in caps} | {'/help'}


def shortcut_catalog(executor=None, language='fr'):
    allowed = permitted_commands(executor)
    en = language == 'en'
    items = []
    for command, _, resource, tool, arguments, fr, english, example_fr, example_en in MODULES:
        if command not in allowed: continue
        help_text = ('Lists authorized records in the active company. Add a description to narrow the search.' if en else
                     'Affiche les résultats autorisés de la société active. Ajoutez une description pour préciser la recherche.')
        if resource == 'payments':
            help_text = ('Lists the latest validated payments in the active company. Add a description for a filtered payment search.' if en else
                         'Affiche les derniers règlements validés de la société active. Ajoutez une description pour une recherche filtrée.')
        if resource == 'users':
            help_text = 'Search the existing staff-only account directory.' if en else 'Recherche dans l’administration des comptes, réservée au personnel autorisé.'
        if resource.startswith('stock') or resource == 'logistics':
            help_text += ' Read and navigation only.' if en else ' Lecture et navigation uniquement.'
        items.append({'command':command, 'title':english if en else fr, 'help':help_text,
                      'example':command + (' ' + (example_en if en else example_fr) if (example_en if en else example_fr) else '')})
    for command, _, fr, english, help_fr, help_en, example_fr, example_en in EXTRA:
        if command in allowed:
            items.append({'command':command, 'title':english if en else fr, 'help':help_en if en else help_fr,
                          'example':command + (' ' + (example_en if en else example_fr) if (example_en if en else example_fr) else '')})
    return items


def usage(command, executor=None, language='fr'):
    for item in shortcut_catalog(executor, language):
        if item['command'] == command:
            prefix = 'Example: ' if language == 'en' else 'Exemple : '
            return f"{command} — {item['title']}\n{item['help']}\n{prefix}{item['example']}"
    raise ChatAIError('PERMISSION_DENIED')


def module_access_action(text, executor, interface_language='fr'):
    """Exact capability questions only; never infer privileges from user text."""
    import re
    from chat_ai_assistant.routing import normalized
    words = re.sub(r'\s+', ' ', normalized(text)).strip().rstrip('?! .')
    match = re.fullmatch(r"(?:do you have access to|can you access|as tu acces (?:a|au|aux)|avez vous acces (?:a|au|aux)|as-tu acces (?:a|au|aux)|avez-vous acces (?:a|au|aux)) (?:the |la |le |les |l[’']|module )?(.+)", words)
    if not match: return None
    names = {
        'logistics':'/logistique', 'logistique':'/logistique', 'logistiques':'/logistique',
        'stock':'/stock', 'articles':'/articles', 'products':'/articles', 'produits':'/articles',
        'invoices':'/factures', 'factures':'/factures', 'factures client':'/factures',
        'quotes':'/devis', 'devis':'/devis', 'proformas':'/proformas', 'pro forma invoices':'/proformas',
        'credit notes':'/avoirs', 'avoirs':'/avoirs', 'delivery notes':'/livraisons', 'bons de livraison':'/livraisons',
        'clients':'/clients', 'customers':'/clients', 'users':'/utilisateurs', 'utilisateurs':'/utilisateurs',
        'payments':'/paiements', 'reglements':'/paiements', 'inventories':'/inventaires', 'inventaires':'/inventaires',
        'stock movements':'/mouvements', 'mouvements de stock':'/mouvements', 'stock receipts':'/receptions', 'receptions':'/receptions',
    }
    command = names.get(match.group(1))
    if command is None: return None
    language = 'en' if words.startswith(('do you ', 'can you ')) else 'fr'
    if command not in permitted_commands(executor):
        message = ('This module is not available to the assistant with your current permissions.' if language == 'en' else
                   'Ce module n’est pas accessible à l’assistant avec vos permissions actuelles.')
    else:
        module = next(m for m in MODULES if m[0] == command)
        executor.authorize_resource(module[2])
        message = ('Yes, subject to your existing permissions. ' if language == 'en' else 'Oui, selon vos permissions existantes. ') + usage(command, executor, language)
    return {'tool':'clarify', 'message':message}


def shortcut_search_hint(text):
    """Derive a shortlist hint; never replace the original user message."""
    parts = text.split(maxsplit=1)
    if len(parts) != 2: return text
    command = ALIASES.get(parts[0].casefold(), parts[0].casefold())
    for item in MODULES:
        if item[0] == command:
            return f"Search {item[6]}"
    return text

"""Optional user-facing shortcuts; names/descriptions never stand in for record IDs."""
import re

NUMBER = re.compile(r"^\d{1,10}/\d{2,4}$")
USAGE = {
    '/voir': '/voir — Rechercher un document\nDécrivez le type de document, le client, le produit ou la période. Vous pourrez choisir parmi les résultats. Aucun identifiant technique à retenir.\nExemple : /voir devis du client Atlas avec peinture',
    '/factures': '/factures — Retrouver des factures\nVoici les factures récentes de la société active. Ajoutez un client, un produit ou une période pour préciser la recherche.\nExemple : /factures du client Atlas en septembre 2026',
    '/clients': '/clients — Rechercher un client\nVoici les premiers clients accessibles. Ajoutez un nom ou une raison sociale pour trouver un client précis.\nExemple : /clients Atlas',
    '/impayees': '/impayees — Voir les factures impayées\nCette commande affiche les factures de la société active avec un solde restant. Elle ne nécessite aucun argument.\nExemple de recherche plus précise : /voir factures impayées du client Atlas',
    '/paiements': '/paiements — Consulter les règlements\nCette commande affiche les derniers paiements validés de la société active. Elle ne nécessite aucun argument.\nExemple de question plus précise : Quels paiements avons-nous reçus en septembre 2026 ?',
    '/pdf': '/pdf — Télécharger un document\nDécrivez le document recherché, puis choisissez le bouton PDF du résultat. Le téléchargement dépend de vos droits d’impression.\nExemple : /pdf facture du client Atlas',
    '/modifier': '/modifier — Modifier un document\nDécrivez le document recherché, puis sélectionnez le résultat à modifier. Vos droits seront vérifiés.\nExemple : /modifier devis du client Atlas avec peinture',
    '/supprimer': '/supprimer — Supprimer un document\nDécrivez le document recherché, sélectionnez le résultat, puis confirmez sa suppression. Aucune suppression sans confirmation et sans les droits correspondants.\nExemple : /supprimer devis du client Atlas avec peinture',
    '/bilan': '/bilan — Consulter une synthèse\nPrécisez la mesure et la période. Mesures : facture (TTC net des avoirs), encaissements, solde, nombre. Périodes : mois, annee, mois-precedent, annee-precedente. Devise facultative : MAD, EUR ou USD.\nExemple : /bilan encaissements mois MAD',
}
ALIASES = {'/chercher': '/voir', '/impayées': '/impayees'}


def shortcut_action(text):
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

    if command in ('/aide', '/help'):
        return clarify('Les raccourcis indiquent ce que vous voulez faire. Vous pouvez aussi écrire normalement.\n'
            '/voir : rechercher un document\n/factures : retrouver des factures\n/clients : rechercher un client\n'
            '/impayees : voir les factures impayées\n/paiements : consulter les règlements\n'
            '/pdf : télécharger un document\n/modifier : modifier un document\n/supprimer : supprimer avec confirmation\n'
            '/bilan : consulter une synthèse\nEnvoyez une commande seule pour voir son utilisation et un exemple. Les actions dépendent de vos droits.')
    if not argument and command in ('/voir', '/pdf', '/modifier', '/supprimer', '/bilan'):
        return clarify(USAGE[command])
    if command == '/factures':
        return None if argument else action('search_invoices', usage=USAGE[command])
    if command == '/impayees':
        return None if argument else action('search_invoices', usage=USAGE[command], unpaid=True)
    if command == '/clients':
        return action('search_clients', usage=USAGE[command] if not argument else None, query=argument)
    if command == '/paiements':
        return None if argument else action('list_payments', usage=USAGE[command])
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
            return clarify(USAGE[command])
        return action('financial_summary', metric=metrics[fields[0]], period=periods[fields[1]], currency=fields[2].upper() if len(fields) == 3 else 'MAD')
    return clarify('Commande inconnue. Envoyez /aide pour afficher les raccourcis disponibles et leur utilisation.')

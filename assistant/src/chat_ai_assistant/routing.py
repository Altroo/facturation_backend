"""Small English/French tool shortlist; authorization always remains in the registry.

An unrecognized request retains the full permitted catalogue. This is prompt-size
selection, never a permission decision and never an inferred database operation.
"""
import re
import unicodedata


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


FAMILIES = {
    'search_documents': ('proforma', 'pro forma', 'pro-forma', 'avoir', 'credit note', 'delivery note', 'bon de livraison', 'bons de livraison'),
    'search_quotes': ('devis', 'quote', 'quotation'),
    'search_invoices': ('facture', 'invoice', 'impaye', 'unpaid'),
    'search_clients': ('client', 'customer', 'clientele'),
    'search_articles': ('article', 'product', 'produit', 'service'),
    'search_payments': ('reglement', 'payment', 'paiement'),
    'search_users': ('utilisateur', 'user', 'compte utilisateur'),
    'search_operations': ('stock', 'inventaire', 'inventory', 'logistique', 'logistics', 'reception', 'receipt', 'movement', 'mouvement', 'warehouse'),
    'financial_summary': ('encaisse', 'collected', 'received', 'revenue', 'chiffre', 'solde', 'balance', 'combien', 'how much', 'how many', 'nombre', 'number of', 'profit', 'benefice', 'gagne', 'money'),
}
COMMON = {'knowledge', 'navigate', 'previous_results'}


def shortlist(text, permitted_tools, context=None):
    words = normalized(text)
    matches = {name for name, terms in FAMILIES.items() if any(normalized(term) in words for term in terms)}
    # A customer/product qualifying a document query does not need a separate
    # customer/product search; document tools support those filters themselves.
    documents = matches & {'search_documents', 'search_quotes', 'search_invoices'}
    if documents:
        matches -= {'search_clients', 'search_articles'}
        if matches & {'search_documents', 'search_quotes'}:
            matches.discard('search_invoices')
        if any(term in words for term in ('client de', 'customer of')):
            matches.add('search_clients')
    if not matches:
        return list(permitted_tools)
    names = COMMON | matches
    if documents:
        names.update({'financial_summary','prepare_change'})
    if 'search_invoices' in names or (context or {}).get('current_invoice_id'):
        names.add('get_invoice')
    if 'search_payments' in names:
        names.add('list_payments')
    if any(term in words for term in ('modifi', 'supprim', 'suppress', 'delet', 'remove', 'edit', 'updat', 'change', 'set ', 'mets ')):
        names.add('prepare_change')
    if any(term in words for term in ('pdf', 'print', 'imprim')):
        names.add('invoice_pdf')
    if (context or {}).get('previous_result_type') in {'article','payment','user','stock_balance','stock_movement','stock_receipt','stock_inventory','logistics_order','proforma','credit_note','delivery_note'}:
        names.add('get_record')
    return [tool for tool in permitted_tools if tool.name in names]

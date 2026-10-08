"""Verified Facturation routes. Callers must authorize every target first."""
from chat_ai_assistant.contracts import ChatAIError

ROUTES = {
    'proformas': '/dashboard/facture-pro-forma/',
    'credit_notes': '/dashboard/facture-avoir/',
    'delivery_notes': '/dashboard/bon-de-livraison/',
    'quotes': '/dashboard/devis/', 'invoices': '/dashboard/facture-client/',
    'clients': '/dashboard/clients/', 'payments': '/dashboard/reglements/',
    'articles': '/dashboard/articles/', 'users': '/dashboard/users/',
    'stock': '/dashboard/stock/', 'stock_movements': '/dashboard/stock/movements/',
    'stock_receipts': '/dashboard/stock/receipts/', 'stock_inventories': '/dashboard/stock/inventories/',
    'logistics': '/dashboard/logistique/', 'dashboard': '/dashboard/',
}
DETAILS = {
    'proforma': ROUTES['proformas'], 'credit_note': ROUTES['credit_notes'],
    'delivery_note': ROUTES['delivery_notes'], 'quote': ROUTES['quotes'],
    'invoice': ROUTES['invoices'], 'client': ROUTES['clients'],
    'article': ROUTES['articles'], 'payment': ROUTES['payments'], 'user': ROUTES['users'],
    'stock_balance': ROUTES['stock'], 'stock_movement': ROUTES['stock_movements'],
    'stock_receipt': ROUTES['stock_receipts'], 'stock_inventory': ROUTES['stock_inventories'],
    'logistics_order': ROUTES['logistics'],
}
# Mutations outside these verified document forms are not exposed by this adapter.
DETAILS.update({resource + '_edit': DETAILS[resource] for resource in
                ('invoice', 'client', 'quote', 'proforma', 'credit_note', 'delivery_note')})


class ChatAINavigationResolver:
    @staticmethod
    def resolve(resource, company_id, identifier=None):
        if type(company_id) is not int or not 1 <= company_id <= 2147483647:
            raise ChatAIError('INVALID_ARGUMENTS')
        if resource in DETAILS and type(identifier) is int and 0 < identifier <= 2147483647:
            route = DETAILS[resource] + str(identifier) + '/' + ('edit/' if resource.endswith('_edit') else '')
        elif resource in ROUTES and identifier is None:
            route = ROUTES[resource]
        else:
            raise ChatAIError('INVALID_ARGUMENTS')
        # Native staff account administration is global, not a company-owned page.
        path = route if resource in ('user', 'users') else route + '?company_id=' + str(company_id)
        return {'application': 'facturation', 'resource': resource, 'identifier': identifier,
                'company_id': company_id, 'path': path}

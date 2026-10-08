"""Visible labels verified against Facturation translations and stock forms."""
RESOURCE_LABELS = {
    'invoice':'Facture client', 'quote':'Devis', 'proforma':'Facture pro forma',
    'credit_note':"Facture d’avoir", 'delivery_note':'Bon de livraison', 'client':'Client',
    'article':'Article', 'payment':'Règlement', 'user':'Utilisateur',
    'stock_balance':'Stock', 'stock_movement':'Mouvement de stock',
    'stock_receipt':'Réception', 'stock_inventory':'Inventaire', 'logistics_order':'Dossier logistique',
}
# Form labels omit only the required-field asterisk. Read-only totals and
# stock values use the existing list/detail labels when there is no form field.
FIELD_LABELS = {
    'remarque':'Remarque', 'termes_paiement':'Termes de paiement',
    'date_echeance':"Date d'échéance", 'raison_sociale':'Raison sociale',
    'nom':'Nom', 'prenom':'Prénom', 'adresse':'Adresse',
    'numero_facture':'Numéro', 'date_facture':'Date de la facture',
    'numero_devis':'Numéro', 'date_devis':'Date du devis',
    'numero_avoir':'Numéro', 'date_avoir':"Date de l'avoir",
    'numero_bon_livraison':'Numéro', 'date_bon_livraison':'Date du bon de livraison',
    'prix_vente':'Prix de vente', 'prix_achat':"Prix d'achat", 'type_article':'Type',
    'physical_quantity':'Physique', 'reserved_quantity':'Réservé',
    'available_quantity':'Disponible', 'incoming_quantity':'Entrant',
    'projected_quantity':'Projeté', 'stock_minimum':'Minimum',
    'balance_after':'Stock après mouvement', 'expected_quantity':'Quantité attendue',
    'counted_quantity':'Quantité comptée', 'invoiced_net_ttc':'Facturé TTC net des avoirs',
    'invoice_count':'Nombre de factures', 'total_ttc_apres_remise':'Total TTC après remise',
    'total_ttc':'TOTAL TTC', 'total_ht':'TOTAL HT', 'payment_status':'Statut paiement',
    'client_name':'Client', 'product_name':'Article', 'date_from':'Date de début',
    'date_to':'Date de fin', 'is_active':'Compte Active', 'is_staff':'Compte Administrateur',
}


def selected_action_text(operation, resource):
    action = {'edit':'Modifier', 'delete':'Supprimer'}.get(operation)
    label = RESOURCE_LABELS.get(resource)
    return f'{action} · {label} sélectionné' if action and label else 'Document sélectionné'


# These overrides follow src/translations/en.ts. Stock forms currently use
# hardcoded French labels, so those labels intentionally stay the same.
ENGLISH_FORM_LABELS = {
    'remarque':'Remark', 'termes_paiement':'Payment terms', 'date_echeance':'Due date',
    'raison_sociale':'Company name', 'nom':'Last name', 'prenom':'First name', 'adresse':'Address',
    'numero_facture':'Number', 'date_facture':'Invoice date',
    'numero_devis':'Number', 'date_devis':'Quote date',
    'numero_avoir':'Number', 'date_avoir':'Credit note date',
    'numero_bon_livraison':'Number', 'date_bon_livraison':'Delivery note date',
    'prix_vente':'Selling price', 'prix_achat':'Purchase price', 'type_article':'Type',
    'invoice_count':'Invoice count', 'total_ttc_apres_remise':'Total incl. tax after discount',
    'total_ttc':'TOTAL INCL. TAX', 'total_ht':'TOTAL EXCL. TAX', 'payment_status':'Payment status',
    'client_name':'Client', 'product_name':'Article', 'date_from':'Start date', 'date_to':'End date',
    'is_active':'Active account', 'is_staff':'Administrator account',
}

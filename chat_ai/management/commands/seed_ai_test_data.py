"""Synthetic local E2E fixtures; refuses all other databases/settings."""
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from django.db import transaction
from account.models import CustomUser,Role,Membership
from company.models import Company
from client.models import Client
from article.models import Article
from facture_client.models import FactureClient,FactureClientLine
from facture_proforma.models import FactureProForma, FactureProFormaLine
from facture_avoir.models import FactureAvoir, FactureAvoirLine
from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine
from devi.models import Devi, DeviLine
from parameter.models import Emplacement
from stock.models import StockBalance, StockMovement, StockReceipt, StockReceiptLine, InventorySession, InventoryLine
from logistique.models import LogisticsOrder, LogisticsOrderLine, LogisticsOrderProforma
class Command(BaseCommand):
    @transaction.atomic
    def handle(self,*args,**kwargs):
        if settings.SETTINGS_MODULE!='facturation_backend.settings_ai_test' or settings.DATABASES['default']['NAME']!='chat_ai_facturation_dev':raise CommandError('Synthetic local database only.')
        for name in ('Alpha','Beta'):
            company,_=Company.objects.get_or_create(ICE='AI-E2E-'+name,defaults={'raison_sociale':'AI Test '+name})
            client,_=Client.objects.get_or_create(company=company,code_client='AI-E2E',defaults={'raison_sociale':'Demo '+name,'client_type':'PM'})
            article,_=Article.objects.get_or_create(company=company,reference='AI-E2E',defaults={'designation':'Synthetic test item','prix_achat':80,'prix_vente':100,'tva':20})
            for label,role_name in [('editor','Caissier'),('reader','Lecture')]:
                email=f'ai-{label}@example.invalid'
                user,_=CustomUser.objects.get_or_create(email=email,defaults={'first_name':'AI Test','last_name':label,'is_active':True})
                user.set_password('Synthetic-only-2026!');user.save()
                role,_=Role.objects.get_or_create(name=role_name)
                if name=='Alpha' or label=='editor':Membership.objects.update_or_create(user=user,company=company,defaults={'role':role})
            invoice,_=FactureClient.objects.get_or_create(client=client,numero_facture='0901/26' if name=='Alpha' else '0902/26',defaults={'date_facture':timezone.localdate(),'statut':'Accepté','created_by_user':user})
            FactureClientLine.objects.get_or_create(facture_client=invoice,article=article,defaults={'prix_achat':80,'prix_vente':100,'quantity':1})
            actor=CustomUser.objects.get(email='ai-editor@example.invalid')
            common={'client':client,'company':company,'created_by_user':actor,'statut':'Brouillon'}
            line_values={'article':article,'prix_achat':80,'prix_vente':100,'quantity':1}
            quote,_=Devi.objects.get_or_create(company=company,numero_devis='0910/26',defaults={**common,'date_devis':timezone.localdate()})
            DeviLine.objects.get_or_create(devis=quote,article=article,defaults=line_values)
            proforma,_=FactureProForma.objects.get_or_create(company=company,numero_facture='0920/26',defaults={**common,'date_facture':timezone.localdate()})
            source,_=FactureProFormaLine.objects.get_or_create(facture_pro_forma=proforma,article=article,defaults=line_values)
            credit,_=FactureAvoir.objects.get_or_create(company=company,numero_avoir='0930/26',defaults={**common,'date_avoir':timezone.localdate(),'facture_origine':invoice,'motif_avoir':'remise'})
            FactureAvoirLine.objects.get_or_create(facture_avoir=credit,article=article,defaults=line_values)
            delivery,_=BonDeLivraison.objects.get_or_create(company=company,numero_bon_livraison='0940/26',defaults={**common,'date_bon_livraison':timezone.localdate()})
            BonDeLivraisonLine.objects.get_or_create(bon_de_livraison=delivery,article=article,defaults=line_values)
            location,_=Emplacement.objects.get_or_create(company=company,nom='Dépôt démo '+name)
            balance,_=StockBalance.objects.get_or_create(company=company,article=article,emplacement=location,defaults={'physical_quantity':4})
            StockMovement.objects.get_or_create(balance=balance,movement_type='opening',defaults={'quantity':4,'balance_after':4,'actor':actor})
            order,_=LogisticsOrder.objects.get_or_create(company=company,numero_commande='LOG-DEMO-'+name,defaults={'fournisseur':'Fournisseur démo '+name,'created_by_user':actor})
            LogisticsOrderProforma.objects.get_or_create(commande=order,proforma=proforma)
            order_line,_=LogisticsOrderLine.objects.get_or_create(commande=order,article=article,defaults={'proforma':proforma,'source_line':source,'client':client,'expected_emplacement':location,'quantity':1,'prix_achat':80,'prix_vente':100})
            receipt,_=StockReceipt.objects.get_or_create(company=company,reference='REC-DEMO-'+name,defaults={'logistics_order':order,'created_by':actor})
            StockReceiptLine.objects.get_or_create(receipt=receipt,article=article,defaults={'logistics_line':order_line,'emplacement':location,'quantity':1})
            inventory,_=InventorySession.objects.get_or_create(company=company,reference='INV-DEMO-'+name,defaults={'emplacement':location,'created_by':actor})
            InventoryLine.objects.get_or_create(inventory=inventory,article=article,defaults={'expected_quantity':4,'counted_quantity':4})
        self.stdout.write('Synthetic E2E fixtures prepared in chat_ai_facturation_dev only.')

from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from account.models import Membership
from article.models import Article
from parameter.models import Marque, Emplacement
from core.constants import CURRENCY_CHOICES
from .serializers import LogisticsSupplierProformaReviewSerializer, validate_logistics_document
from .purchase import CONDITIONS, validate_condition


class PurchaseDossierSerializer(serializers.Serializer):
    fournisseur = serializers.CharField(max_length=255, required=False, allow_blank=False)
    fournisseur_email = serializers.EmailField(required=False, allow_blank=True)
    marque = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    responsable = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    date_prevue = serializers.DateField(required=False, allow_null=True)
    date_commande_client = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        company = self.context["company_id"]
        if self.context.get("create") and not attrs.get("fournisseur"):
            raise serializers.ValidationError({"fournisseur": "Renseignez le fournisseur."})
        if attrs.get("responsable") and not Membership.objects.filter(company_id=company,
            user_id=attrs["responsable"], user__is_active=True).exists():
            raise serializers.ValidationError({"responsable": "Ce responsable n’appartient pas à cette société."})
        if attrs.get("responsable") and not Membership.objects.filter(company_id=company,
            user_id=attrs["responsable"], role__name__in=["Caissier", "Commercial", "Logistique"]).exists():
            raise serializers.ValidationError({"responsable": "Choisissez un responsable autorisé à modifier les dossiers logistiques."})
        if attrs.get("marque") and not Marque.objects.filter(company_id=company, pk=attrs["marque"]).exists():
            raise serializers.ValidationError({"marque": "Cette marque n’appartient pas à cette société."})
        return attrs


class PurchaseLineSerializer(serializers.Serializer):
    article = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=Decimal("0.001"))
    prix_achat = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    expected_emplacement = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class PurchaseProformaSerializer(LogisticsSupplierProformaReviewSerializer):
    condition_achat = serializers.ChoiceField(choices=list(CONDITIONS), required=True)
    lignes = serializers.JSONField(required=False)
    origine_marchandise = serializers.CharField(required=False, allow_blank=True, max_length=255)
    nature_marchandise = serializers.CharField(required=False, allow_blank=True, max_length=255)
    poids_net = serializers.DecimalField(required=False, max_digits=10, decimal_places=2, min_value=0)
    poids_brut = serializers.DecimalField(required=False, max_digits=10, decimal_places=2, min_value=0)
    volume = serializers.DecimalField(required=False, max_digits=10, decimal_places=3, min_value=0)

    def validate(self, attrs):
        order = self.context["order"]
        attrs["conditions_paiement"] = CONDITIONS[attrs["condition_achat"]][0]
        attrs = super().validate(attrs)
        validate_condition(attrs["condition_achat"], attrs.get("montant_proforma_fournisseur", order.montant_proforma_fournisseur))
        raw_lines = attrs.get("lignes")
        if raw_lines is not None:
            lines = PurchaseLineSerializer(data=raw_lines, many=True, allow_empty=False)
            lines.is_valid(raise_exception=True)
            article_ids = {line["article"] for line in lines.validated_data}
            if Article.objects.filter(pk__in=article_ids, company_id=order.company_id).count() != len(article_ids):
                raise serializers.ValidationError({"lignes": "Un article est introuvable ou appartient à une autre société."})
            location_ids = {line["expected_emplacement"] for line in lines.validated_data if line.get("expected_emplacement")}
            if Emplacement.objects.filter(pk__in=location_ids, company_id=order.company_id).count() != len(location_ids):
                raise serializers.ValidationError({"lignes": "Un emplacement appartient à une autre société."})
            articles = Article.objects.filter(pk__in=article_ids).select_related("emplacement")
            if any(article.emplacement_id and article.emplacement.company_id != order.company_id for article in articles):
                raise serializers.ValidationError({"lignes": "L’emplacement par défaut d’un article appartient à une autre société."})
            attrs["lignes"] = lines.validated_data
        elif not order.lignes.exists():
            raise serializers.ValidationError({"lignes": "Ajoutez les articles, quantités et prix de la proforma fournisseur."})
        return attrs


class PurchaseProgressSerializer(serializers.Serializer):
    date_expedition_prevue = serializers.DateField(required=False, allow_null=True)
    confirmer_production = serializers.BooleanField(required=False)
    date_expedition_reelle = serializers.DateField(required=False, allow_null=True)
    date_arrivee_maroc = serializers.DateField(required=False, allow_null=True)
    documents_remis_banque_le = serializers.DateField(required=False, allow_null=True)
    date_reelle = serializers.DateField(required=False, allow_null=True)
    remarque = serializers.CharField(required=False, allow_blank=True)
    statut = serializers.ChoiceField(required=False, choices=["Production", "Expédition", "Transit", "Dédouanement", "Réception locale", "Livraison client", "Clôture"])
    transport = serializers.CharField(required=False, allow_blank=True, max_length=100)
    documents_originaux_requis = serializers.BooleanField(required=False)
    statut_documents_originaux = serializers.ChoiceField(required=False, choices=["", "Demandé", "Réceptionné", "Retourné pour correction", "Refusé"])
    documents_originaux_file = serializers.FileField(required=False, validators=[validate_logistics_document])
    justificatifs_file = serializers.FileField(required=False, validators=[validate_logistics_document])
    cout_transport = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=0)
    frais_transit = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=0)
    frais_douane = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=0)
    tva = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=0)
    livraison_locale = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=0)
    autres_frais = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=0)

    def validate(self, attrs):
        order = self.context["order"]
        today = timezone.localdate()
        for field in ("date_expedition_reelle", "date_arrivee_maroc", "documents_remis_banque_le", "date_reelle"):
            if attrs.get(field) and attrs[field] > today:
                raise serializers.ValidationError({field: "Une date réelle ne peut pas être dans le futur."})
            if field in attrs and getattr(order, field) and attrs[field] != getattr(order, field):
                raise serializers.ValidationError({field: "Cette date réelle est déjà enregistrée dans l’historique."})
        planned = attrs.get("date_expedition_prevue", order.date_expedition_prevue)
        shipped = attrs.get("date_expedition_reelle", order.date_expedition_reelle)
        old_plan_overdue = bool(order.date_expedition_prevue and order.date_expedition_prevue < today and not order.date_expedition_reelle)
        delay = bool(planned and ((shipped and shipped > planned) or (not shipped and planned < today)))
        existing_explanation = order.process_notes.filter(remarque__startswith=f"Retard d’expédition ({order.date_expedition_prevue}) :").exists()
        changed_plan = "date_expedition_prevue" in attrs and planned != order.date_expedition_prevue
        newly_shipped_late = "date_expedition_reelle" in attrs and not order.date_expedition_reelle and delay
        if ((old_plan_overdue and changed_plan) or (delay and (not existing_explanation or newly_shipped_late))) and not attrs.get("remarque", "").strip():
            raise serializers.ValidationError({"remarque": "Expliquez le retard d’expédition dans une remarque."})
        received = attrs.get("date_reelle", order.date_reelle)
        if received and (not shipped or received < shipped):
            raise serializers.ValidationError({"date_reelle": "La réception doit suivre l’expédition."})
        arrival = attrs.get("date_arrivee_maroc", order.date_arrivee_maroc)
        if arrival and (not shipped or arrival < shipped):
            raise serializers.ValidationError({"date_arrivee_maroc": "L’arrivée au Maroc doit suivre l’expédition."})
        from stock.services import is_product
        if "date_reelle" in attrs and order.company.stock_management_enabled and any(is_product(line.article) for line in order.lignes.all()):
            raise serializers.ValidationError({"date_reelle": "La réception réelle est enregistrée lors de la validation des quantités reçues."})
        return attrs

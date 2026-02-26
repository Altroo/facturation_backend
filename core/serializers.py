from re import match

from django.db import transaction
from rest_framework import serializers

from core.constants import ROLE_COMMERCIAL
from core.permissions import get_user_role


def validate_line_currency(data, instance, parent_field_name):
    """
    Validate that line currency matches parent document currency.
    Used by standalone line serializers.

    Args:
        data: Validated data dictionary
        instance: Current instance (for updates) or None (for creates)
        parent_field_name: Name of the parent document field (e.g., 'devis', 'facture_client')

    Raises:
        serializers.ValidationError if currency mismatch
    """
    parent = data.get(parent_field_name) or (
        getattr(instance, parent_field_name) if instance else None
    )
    devise_prix_vente = data.get("devise_prix_vente")

    if parent and devise_prix_vente:
        # If document has lines and a non-default devise, validate currency match
        if parent.lignes.exists() and parent.devise != "MAD":
            if devise_prix_vente != parent.devise:
                raise serializers.ValidationError(
                    {
                        "devise_prix_vente":
                            f"La devise doit correspondre à celle du document ({parent.devise}). "
                            f"Impossible de mélanger les devises."
                    }
                )


def update_document_devise_on_first_line(parent, devise_prix_vente):
    """
    Update document devise when creating the first line.

    Args:
        parent: Parent document instance
        devise_prix_vente: Currency from the line being created
    """
    if parent and not parent.lignes.exists() and parent.devise == "MAD":
        parent.devise = devise_prix_vente
        parent.save(update_fields=["devise"])


class BaseListSerializer(serializers.ModelSerializer):
    """Abstract list serializer with common total fields and helpers."""

    client_name = serializers.StringRelatedField(source="client", read_only=True)
    mode_paiement_name = serializers.CharField(
        source="mode_paiement.nom", read_only=True
    )
    created_by_user_name = serializers.SerializerMethodField()
    lignes_count = serializers.SerializerMethodField()

    total_ht = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_tva = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_ttc = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_ttc_apres_remise = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    @staticmethod
    def get_created_by_user_name(obj):
        if obj.created_by_user:
            return (
                f"{obj.created_by_user.first_name} {obj.created_by_user.last_name}".strip()
                or obj.created_by_user.email
            )
        return None

    @staticmethod
    def get_lignes_count(obj):
        # Use len() on the prefetch cache when available (avoids an extra
        # COUNT query per row).  Falls back to .count() when lignes is not
        # prefetched.
        if hasattr(obj, '_prefetched_objects_cache') and 'lignes' in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache['lignes'])
        return obj.lignes.count()

    def to_representation(self, instance):
        """Handle None related objects gracefully."""
        representation = super().to_representation(instance)

        # Handle None mode_paiement
        if instance.mode_paiement is None:
            representation["mode_paiement_name"] = None

        return representation

    class Meta:
        abstract = True


class BaseDetailSerializer(serializers.ModelSerializer):
    """Abstract detail serializer with common fields, validation, and totals."""

    client_name = serializers.StringRelatedField(source="client", read_only=True)
    created_by_user_name = serializers.SerializerMethodField()
    created_by_user_id = serializers.IntegerField(
        source="created_by_user.id", read_only=True
    )
    mode_paiement_name = serializers.CharField(
        source="mode_paiement.nom", read_only=True
    )

    total_ht = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_tva = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_ttc = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_ttc_apres_remise = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    @staticmethod
    def get_created_by_user_name(obj):
        if obj.created_by_user:
            return (
                f"{obj.created_by_user.first_name} {obj.created_by_user.last_name}".strip()
                or obj.created_by_user.email
            )
        return None

    def to_representation(self, instance):
        """Handle None related objects gracefully."""
        representation = super().to_representation(instance)

        # Handle None mode_paiement
        if instance.mode_paiement is None:
            representation["mode_paiement_name"] = None

        # Handle None created_by_user
        if instance.created_by_user is None:
            representation["created_by_user_id"] = None

        return representation

    def validate(self, data):
        """
        Validate document-level remise fields:
        - remise must be >= 0
        - if remise_type == 'Pourcentage' then 0 <= remise <= 100
        """
        remise = data.get("remise")
        remise_type = data.get(
            "remise_type",
            (
                getattr(self.instance, "remise_type", "")
                if getattr(self, "instance", None)
                else ""
            ),
        )

        if remise is None:
            return data

        try:
            remise_val = float(remise)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"remise": "Valeur de remise invalide."})

        if remise_val < 0:
            raise serializers.ValidationError(
                {"remise": "La remise doit être positive ou nulle."}
            )

        if remise_type == "":
            return data

        if remise_type == "Pourcentage":
            if not 0 <= remise_val <= 100:
                raise serializers.ValidationError(
                    {"remise": "La remise en pourcentage doit être entre 0 et 100."}
                )
        elif remise_type == "Fixe":
            pass
        else:
            raise serializers.ValidationError(
                {"remise_type": "Type de remise invalide."}
            )

        return data

    def get_numero_field_name(self):
        """Return the numero field name (e.g., 'numero_devis', 'numero_facture'). Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_numero_field_name()")

    def validate_numero(self, value):
        """Validate numero format: 0001/25"""
        if not match(r"^\d{4}/\d{2}$", value):
            field_name = self.get_numero_field_name()
            raise serializers.ValidationError(
                f"Format de {field_name.replace('_', ' ')} invalide. Format attendu: 0001/25"
            )
        return value

    class Meta:
        abstract = True


class BaseLineWriteSerializer(serializers.ModelSerializer):
    """Abstract write serializer for nested lines."""

    id = serializers.IntegerField(required=False)

    def validate(self, data):
        # Check if Commercial user is trying to modify prix_vente
        request = self.context.get("request")
        if request and request.user:

            # Try to get company_id from parent serializer context
            company_id = self.context.get("company_id")
            if company_id:
                role = get_user_role(request.user, company_id)
                if role == ROLE_COMMERCIAL and "prix_vente" in data:
                    # For updates, check if prix_vente is being changed
                    if self.instance:
                        if data.get("prix_vente") != self.instance.prix_vente:
                            raise serializers.ValidationError(
                                "Les utilisateurs Commercial ne peuvent pas modifier le prix de vente."
                            )
                    # For creates, Commercial cannot set custom prix_vente
                    # They must use the article's default prix_vente
                    elif "article" in data:
                        article = data["article"]
                        if data.get("prix_vente") != article.prix_vente:
                            raise serializers.ValidationError(
                                "Les utilisateurs Commercial ne peuvent pas définir un prix de vente personnalisé."
                            )

        # Validate currency consistency with document
        document_devise = self.context.get("document_devise")
        article = data.get("article")
        devise_prix_achat = data.get("devise_prix_achat")
        devise_prix_vente = data.get("devise_prix_vente")

        # Auto-set devise_prix_achat from article if not provided
        if article and not devise_prix_achat:
            data["devise_prix_achat"] = article.devise_prix_achat

        # Auto-set devise_prix_vente from document if not provided
        if document_devise and not devise_prix_vente:
            data["devise_prix_vente"] = document_devise
            devise_prix_vente = document_devise

        # If document has no devise set yet (first line), we'll set it from this line
        # Otherwise, validate that line currency matches document currency
        if document_devise and devise_prix_vente:
            if devise_prix_vente != document_devise:
                raise serializers.ValidationError(
                    {
                        "devise_prix_vente":
                            f"La devise doit correspondre à celle du document ({document_devise}). "
                            f"Impossible de mélanger les devises."
                    }
                )

        if data["prix_vente"] < data["prix_achat"]:
            raise serializers.ValidationError(
                "Le prix de vente doit être supérieur ou égal au prix d'achat."
            )

        remise = data.get("remise", 0)
        remise_type = data.get("remise_type") or "Pourcentage"
        quantity = data.get("quantity", 1)

        if quantity <= 0:
            raise serializers.ValidationError(
                "La quantité doit être supérieure à 0."
            )

        line_total = data["prix_vente"] * quantity

        if remise < 0:
            raise serializers.ValidationError("La remise doit être positive ou nulle.")

        if remise_type == "Pourcentage":
            if not 0 <= remise <= 100:
                raise serializers.ValidationError(
                    "La remise en pourcentage doit être entre 0 et 100."
                )
        elif remise_type == "Fixe":
            if remise > line_total:
                raise serializers.ValidationError(
                    "La remise fixe ne peut pas dépasser le total de la ligne."
                )
        else:
            raise serializers.ValidationError("Type de remise invalide.")

        return data

    class Meta:
        abstract = True


class BaseCreateSerializer(BaseDetailSerializer):
    """Abstract create serializer with create and to_representation logic."""

    def get_line_model_class(self):
        """Return the line model class. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_line_model_class()")

    def get_line_relation_field(self):
        """Return the foreign key field name (e.g., 'devis', 'facture_client'). Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_line_relation_field()")

    def get_line_serializer_class(self):
        """Return the line serializer class for representation. Override in subclasses."""
        raise NotImplementedError(
            "Subclasses must implement get_line_serializer_class()"
        )

    def validate(self, data):
        """Add company_id and document_devise to context for nested line serializers."""
        data = super().validate(data)
        # Store company_id in context for line serializers to access
        if "client" in data:
            self.context["company_id"] = data["client"].company_id
        # Store document_devise if it exists (for line validation)
        if hasattr(self, "instance") and self.instance:
            self.context["document_devise"] = self.instance.devise
        return data

    def create(self, validated_data):
        lines_data = validated_data.pop("lignes", [])
        instance = super().create(validated_data)

        line_model = self.get_line_model_class()
        relation_field = self.get_line_relation_field()

        # If lines are being added and document has no devise yet, set it from first line
        if lines_data and instance.devise == "MAD":
            first_line = lines_data[0]
            if "devise_prix_vente" in first_line:
                instance.devise = first_line["devise_prix_vente"]
                instance.save(update_fields=["devise"])

        # Ensure all lines have correct devise_prix_vente and devise_prix_achat
        for line_data in lines_data:
            line_data.pop("id", None)
            # Auto-set devise_prix_vente from document if not provided or if MAD
            if "devise_prix_vente" not in line_data or line_data.get("devise_prix_vente") == "MAD":
                line_data["devise_prix_vente"] = instance.devise
            # Auto-set devise_prix_achat from article if not provided or if MAD
            if "article" in line_data:
                article = line_data["article"]
                if "devise_prix_achat" not in line_data or line_data.get("devise_prix_achat") == "MAD":
                    line_data["devise_prix_achat"] = article.devise_prix_achat
            line_model.objects.create(**{relation_field: instance}, **line_data)

        return instance

    def to_representation(self, instance):
        """Include detailed lignes in response.

        Uses ``select_related('article')`` to avoid N+1 queries when the
        line serializer accesses ``article.designation`` / ``article.reference``.
        """
        representation = super().to_representation(instance)
        line_serializer_class = self.get_line_serializer_class()
        representation["lignes"] = line_serializer_class(
            instance.lignes.select_related("article").all(), many=True, context=self.context
        ).data
        return representation

    class Meta:
        abstract = True


class BaseDetailUpdateSerializer(BaseCreateSerializer):
    """Abstract detail serializer with upsert update logic for nested lines."""

    def validate(self, data):
        """Add company_id and document_devise to context for nested line serializers."""
        data = super().validate(data)
        # Store company_id in context for line serializers to access
        if hasattr(self, "instance") and self.instance:
            self.context["company_id"] = self.instance.client.company_id
            # Store document_devise for line validation
            self.context["document_devise"] = self.instance.devise
        return data

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lignes", None)

        instance = super(BaseCreateSerializer, self).update(instance, validated_data)

        if lines_data is not None:
            with transaction.atomic():
                existing_lines = {line.id: line for line in instance.lignes.all()}
                incoming_ids = set()
                line_model = self.get_line_model_class()
                relation_field = self.get_line_relation_field()

                # If document has no lines yet, and we're adding some, set devise from first line
                if not existing_lines and lines_data and instance.devise == "MAD":
                    first_line = lines_data[0]
                    if "devise_prix_vente" in first_line:
                        instance.devise = first_line["devise_prix_vente"]
                        instance.save(update_fields=["devise"])

                # Suppress per-line signal recalc to avoid O(N²) queries.
                # We will call recalc_totals() once after all lines are persisted.
                instance._skip_line_recalc = True

                try:
                    for line_data in lines_data:
                        line_id = line_data.get("id")

                        # Auto-set devise_prix_vente from document if not provided or if MAD
                        if "devise_prix_vente" not in line_data or line_data.get("devise_prix_vente") == "MAD":
                            line_data["devise_prix_vente"] = instance.devise
                        # Auto-set devise_prix_achat from article if not provided or if MAD
                        if "article" in line_data:
                            article = line_data["article"]
                            if "devise_prix_achat" not in line_data or line_data.get("devise_prix_achat") == "MAD":
                                line_data["devise_prix_achat"] = article.devise_prix_achat

                        if line_id and line_id in existing_lines:
                            line_obj = existing_lines[line_id]
                            for field, value in line_data.items():
                                if field != "id":
                                    setattr(line_obj, field, value)
                            line_obj.save()
                            incoming_ids.add(line_id)
                        else:
                            create_data = {k: v for k, v in line_data.items() if k != "id"}
                            line_model.objects.create(
                                **{relation_field: instance}, **create_data
                            )

                    ids_to_delete = set(existing_lines.keys()) - incoming_ids
                    if ids_to_delete:
                        line_model.objects.filter(id__in=ids_to_delete).delete()
                finally:
                    instance._skip_line_recalc = False

                # Single recalc after all line operations are complete
                instance.recalc_totals()
                instance.save(
                    update_fields=[
                        "total_ht",
                        "total_tva",
                        "total_ttc",
                        "total_ttc_apres_remise",
                    ]
                )

        return instance

    class Meta:
        abstract = True
